import sys
from os import rmdir, mkdir
from ecdsa import SigningKey, VerifyingKey, Ed25519
from ecdsa.util import sigencode_der, sigdecode_der
from hashlib import sha3_256

DIR = "keys/"
JOURNALISTS = 10

def reset():
	rmdir(DIR)


def load_key(name):
	with open(f"{DIR}/{name}.key", "rb") as f:
		key = SigningKey.from_pem(f.read())


	with open(f"{DIR}/{name}.pem", "rb") as f:
		public_key = VerifyingKey.from_pem(f.read())

	assert(key.verifying_key == public_key)

	return key


def generate_key(name):
	key = SigningKey.generate(curve=Ed25519)

	with open(f"{DIR}/{name}.key", "wb") as f:
		f.write(key.to_pem(format="pkcs8"))

	with open(f"{DIR}/{name}.pem", "wb") as f:
		f.write(key.verifying_key.to_pem())

	return key


def sign_key(signing_pivate_key, signed_public_key, signature_name):
	sig = signing_pivate_key.sign_deterministic(
		signed_public_key.to_string(),
		hashfunc=sha3_256,
		sigencode=sigencode_der
	)
	
	with open(signature_name, "wb") as f:
		f.write(sig)

	return True

def verify_key(signing_public_key, signed_public_key, signature_name):
	with open(signature_name, "rb") as f:
		sig = f.read()
	signing_public_key.verify(sig, signed_public_key.to_string(), sha3_256, sigdecode=sigdecode_der)

def generate_pki():
	try:
		rmdir(DIR)
	except:
		pass
	mkdir(DIR)
	root_key = generate_key("root")
	intermediate_key = generate_key("intermediate")
	sign_key(root_key, intermediate_key.verifying_key, f"{DIR}intermediate.sig")
	journalist_keys = generate_journalists(intermediate_key)
	return root_key, intermediate_key, journalist_keys

def load_pki():
	root_key = load_key("root")
	intermediate_key = load_key("intermediate")
	verify_key(root_key.verifying_key, intermediate_key.verifying_key, f"{DIR}intermediate.sig")
	journalist_keys = []
	for j in range(JOURNALISTS):
		journalist_key = load_key(f"journalists/journalist_{j}")
		journalist_keys.append(journalist_key)
		verify_key(intermediate_key.verifying_key, journalist_key.verifying_key, f"{DIR}journalists/journalist_{j}.sig")
	return root_key, intermediate_key, journalist_keys

def generate_journalists(intermediate_key):
	journalist_keys = []
	mkdir(f"{DIR}/journalists/")
	for j in range(JOURNALISTS):
		journalist_key = generate_key(f"journalists/journalist_{j}")
		journalist_keys.append(journalist_key)
		sign_key(intermediate_key, journalist_key.verifying_key, f"{DIR}journalists/journalist_{j}.sig")
	return journalist_keys

def main():

	root_key, intermediate_key, journalist_keys = generate_pki()
	#root_key, intermediate_key, journalist_keys = load_pki()
	


main()