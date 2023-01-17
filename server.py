import json
import libs.pki
from libs.DiffieHellman import DiffieHellman
from secrets import token_hex
from redis import Redis
from flask import Flask, request

SERVER = "127.0.0.1:5000"
DIR = "keys/"
JOURNALISTS = 10

# bootstrap keys
journalist_verifying_keys = pki.load_and_verify_journalist_verifying_keys()

redis = Redis()
app = Flask(__name__)

@app.route("/")
def index():
    return {"status": "OK"}, 200

########################################################################
@app.route("/simulation/set_source_public_key", methods=["POST"])
def simulation_set_source_public_key():
	assert("source_public_key" in request.json)
	redis.set("simulation:source_public_key", request.json["source_public_key"])
	return {"status": "OK"}, 200

@app.route("/simulation/get_source_public_key", methods=["GET"])
def simulation_get_source_public_key():
	source_public_key = redis.get("simulation:source_public_key")
	if source_public_key is None:
		return {"status": "KO"}, 404
	else:
		return {"source_public_key": int(source_public_key.decode('ascii'))}, 200

@app.route("/simulation/set_source_private_key", methods=["POST"])
def simulation_set_source_private_key():
	assert("simulation:source_private_key" in request.json)
	redis.set("source_private_key", request.json["source_private_key"])
	return {"status": "OK"}, 200

@app.route("/simulation/get_source_private_key", methods=["GET"])
def simulation_get_source_private_key():
	source_private_key = redis.get("simulation:source_private_key")
	if source_private_key is None:
		return {"status": "KO"}, 404
	else:
		return {"source_private_key": int(source_private_key.decode('ascii'))}, 200
########################################################################

@app.route("/send_j2s_message", methods=["POST"])
def send_j2s_message():
	content = request.json
	try:
		assert("message" in content)
		assert("message_public_key" in content)
		assert("message_challenge" in content)
	except:
		return {"status": "KO"}, 400
	message_dict = {
		# encrypted message
		"message": request.json["message"],
		# gj, public key part of the keypar generated by the sending journalist for every message
		"message_public_key": request.json["message_public_key"],
		# gkj, public part computer using the source public key and the per message secret key
		"message_challenge": request.json["message_challenge"]
	}
	# save the journalist to source reply in redis
	redis.set(f"message:{token_hex(32)}", json.dumps(message_dict))
	return {"status": "OK"}, 200

@app.route("/get_message_challenges", methods=["GET"])
def get_messages_challenge():
	s = DiffieHellman()
	# generate a challenge id
	challenge_id = token_hex(32)
	# save it in redis as an expiring key
	redis.setex(f"challenge:{challenge_id}", 120, s.privateKey)
	messages_challenge = []
	# retrieve all the message keys
	message_keys = redis.keys("message:*")
	for message_key in message_keys:
		# retrieve the message and load the json
		message_dict = json.loads(redis.get(message_key).decode('ascii'))
		# calculate the "gkjs" challenge
		messages_challenge.append(pow(message_dict["message_challenge"], s.privateKey, s.prime))

	# return all the message challenges
	# padding to hide the number of meesages to be added later
	response_dict = {"status": "OK", "challenge_id": challenge_id, "message_challenges": messages_challenge}
	return response_dict, 200

@app.route("/send_message_challenges_responses/<challenge_id>", methods=["POST"])
def send_message_challenges_response(challenge_id):
	# retrieve the challenge secret key from the challenge id in redis
	privateKey = redis.get(f"challenge:{challenge_id}")
	if privateKey is not None:
		privateKey = int(privateKey.decode('ascii'))
	else:
		return {"status": "KO"}, 400

	# load the secret key and derive the public key
	s = DiffieHellman(privateKey=privateKey)
	try:
		assert("message_challenges_responses" in request.json)
	except:
		return {"status": "KO"}, 400

	# calculate the inverse of the per request server key
	inv_server = pow(s.privateKey, -1, s.prime - 1)

	# fetch all the messages again from redis
	message_keys = redis.keys("message:*")
	messages = []
	for message_key in message_keys:
		# retrieve the message and load the json
		messages.append({"message_id": message_key[8:].decode('ascii'), "message_public_key": json.loads(redis.get(message_key).decode('ascii'))["message_public_key"]})

	# check all the challenges responses
	potential_messages_public_keys = []
	for message_challenge_response in request.json["message_challenges_responses"]:
		potential_messages_public_keys.append(pow(message_challenge_response, inv_server, s.prime))

	# check if any public key in the computed challenge/responses matches any message and return them
	valid_messages = []
	for message in messages:
		for potential_messages_public_key in potential_messages_public_keys:
			if potential_messages_public_key == message["message_public_key"]:
				valid_messages.append(message["message_id"])
	if len(valid_messages) > 0:
		return {"status": "OK", "messages": valid_messages}, 200
	return "SAAAAAD", 404


