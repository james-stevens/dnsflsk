#! /usr/bin/python3

import flask
import dns


app = flask.Flask("DNS/Rest/api")


@app.errorhandler(404)
def not_found(error):
    return flask.make_response(flask.jsonify({'error': 'Not found'}), 404)


@app.route('/dns/api/v1.0/resolv/', methods=['GET'])
@app.route('/dns/api/v1.0/resolv', methods=['GET'])
def resolver():
	print(flask.request.args.get("name"))
	return flask.jsonify({ "answer": "This is my answer"})


@app.route("/dns/api/v1.0/")
@app.route("/dns/api/v1.0")
def v1():
    return "Welcome to the DNS/API v1.0"


@app.route("/")
def hello():
    return "Welcome to the DNS/API"


if __name__ == "__main__":
    app.run()
