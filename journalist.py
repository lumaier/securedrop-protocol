import argparse
import json
from base64 import b64encode
from datetime import datetime
from os import listdir
from time import time

import requests
from ecdsa import SigningKey

import commons
import pki


def add_ephemeral_keys(journalist_key, journalist_id, journalist_uid):
    ephemeral_keys = []
    for key in range(commons.ONETIMEKEYS):
        # Generate an ephemeral key, sign it and load the signature
        ephemeral_sig, ephemeral_key = pki.generate_ephemeral(journalist_key, journalist_id, journalist_uid)
        ephemeral_keys.append({"ephemeral_key": b64encode(ephemeral_key.verifying_key.to_string()).decode("ascii"),
                               "ephemeral_sig": b64encode(ephemeral_sig).decode("ascii")})

    # Send both to server, the server veifies the signature and the trust chain prior ro storing/publishing
    response = requests.post(f"http://{commons.SERVER}/ephemeral_keys", json={"journalist_uid": journalist_uid,
                                                                              "ephemeral_keys": ephemeral_keys})

    return (response.status_code == 200)


# Load the journalist ephemeral keys from the journalist key dirrectory.
# On an actual implementation this would more likely be a sqlite (or sqlcipher)
# database.
def load_ephemeral_keys(journalist_key, journalist_id, journalist_uid):
    ephemeral_keys = []
    key_file_list = listdir(f"{commons.DIR}journalists/{journalist_uid}/")
    for file_name in key_file_list:
        if file_name.endswith('.key'):
            with open(f"{commons.DIR}journalists/{journalist_uid}/{file_name}", "rb") as f:
                key = f.read()
            ephemeral_keys.append(SigningKey.from_pem(key))
    return ephemeral_keys


# Try all the ephemeral keys to build an encryption shared secret to decrypt a message.
# This is inefficient, but on an actual implementation we would discard already used keys
def decrypt_message(ephemeral_keys, message):
    for ephemeral_key in ephemeral_keys:
        message_plaintext = commons.decrypt_message_ciphertext(
            ephemeral_key, message["message_public_key"],
            message["message_ciphertext"])
        if message_plaintext:
            return message_plaintext


def journalist_reply(message, reply, journalist_uid):
    # This function builds the per-message keys and returns a nacl encrypting box
    message_public_key, message_challenge, box = commons.build_message(
        message["source_challenge_public_key"],
        message["source_encryption_public_key"])

    # The actual message struct varies depending on the sending party.
    # Still it is client controlled, so in each client we shall watch out a bit.
    message_dict = {"message": reply,
                    # do we want to sign messages? how do we attest source authoriship?
                    "sender": journalist_uid,
                    # "receiver": "source_id_placeholder",
                    # we could list the journalists involved in the conversation here
                    # if the source choose not to pick everybody
                    "group_members": [],
                    "timestamp": int(time())}

    message_ciphertext = b64encode(
        box.encrypt((json.dumps(message_dict)).ljust(1024).encode('ascii'))
    ).decode("ascii")

    # Send the message to the server API using the generic /send endpoint
    commons.send_message(message_ciphertext, message_public_key, message_challenge)


def main(args):
    # Get and check the journalist number we are impersonating
    journalist_id = args.journalist
    assert (journalist_id >= 0 and journalist_id < commons.JOURNALISTS)

    journalist_uid, journalist_sig, journalist_key, journalist_chal_sig, journalist_chal_key = pki.load_and_verify_journalist_keypair(journalist_id)

    if args.action == "upload_keys":
        journalist_uid = commons.add_journalist(journalist_key, journalist_sig, journalist_chal_key, journalist_chal_sig)

        # Generate and upload a bunch (30) of ephemeral keys
        add_ephemeral_keys(journalist_key, journalist_id, journalist_uid)

    elif args.action == "fetch":
        # Check if there are messages
        messages_list = commons.fetch_messages_id(journalist_chal_key)

        nmessages = len(messages_list)

        if nmessages > 0:
            print(f"[+] Found {nmessages} message(s)")
            for message_id in messages_list:
                print(f"\t{message_id}")
            print()
        else:
            print("[-] There are no messages")
            print()

    elif args.action == "read":
        message_id = args.id
        message = commons.get_message(message_id)
        ephemeral_keys = load_ephemeral_keys(journalist_key, journalist_id, journalist_uid)
        message_plaintext = decrypt_message(ephemeral_keys, message)

        if message_plaintext:
            print(f"[+] Successfully decrypted message {message_id}")
            print()
            print(f"\tID: {message_id}")
            # print(f"\tFrom: {message_plaintext['sender']}")
            print(f"\tDate: {datetime.fromtimestamp(message_plaintext['timestamp'])}")
            for attachment in message_plaintext["attachments"]:
                print(f"\tAttachment: name={attachment['name']};size={attachment['size']};parts_count={attachment['parts_count']}")
            print(f"\tText: {message_plaintext['message']}")
            print()

    elif args.action == "reply":
        message_id = args.id
        message = commons.get_message(message_id)
        ephemeral_keys = load_ephemeral_keys(journalist_key, journalist_id, journalist_uid)
        message_plaintext = decrypt_message(ephemeral_keys, message)
        journalist_reply(message_plaintext, args.message, journalist_uid)

    elif args.action == "delete":
        message_id = args.id
        commons.delete_message(message_id)
        print(f"[+] Message {message_id} deleted")
        print()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-j", "--journalist", help="Journalist number", type=int, choices=range(0, commons.JOURNALISTS), metavar=f"[0, {commons.JOURNALISTS - 1}]", required=True)
    parser.add_argument("-a", "--action", help="Action to perform", default="fetch", choices=["upload_keys", "fetch", "read", "reply", "delete"])
    parser.add_argument("-i", "--id", help="Message id")
    parser.add_argument("-m", "--message", help="Plaintext message content for replies")
    args = parser.parse_args()
    main(args)
