#! /usr/bin/python3

import flask
import dns
import re


is_valid_host_re = re.compile(r'^([0-9a-z][-\w]*[0-9a-z]\.)+[a-z0-9\-]{2,15}$')

def is_valid_host(host):
	return is_valid_host_re.match(host) != None


def abort(err_no, message):
	response = flask.jsonify({'error': message})
	response.status_code = err_no
	return response


app = flask.Flask("DNS/Rest/api")


@app.route('/dns/api/v1.0/resolv/', methods=['GET'])
@app.route('/dns/api/v1.0/resolv', methods=['GET'])
def resolver():
    dns_name = flask.request.args.get("name")
    dns_type = flask.request.args.get("type", default=1, type=int)

    if dns_name is None:
        return abort(400, "'name' parameter is missing")

    if not is_valid_host(dns_name):
        return abort(400, "'name' parameter is not a valid FQDN")

    return flask.jsonify({"name": dns_name, "type": dns_type})


@app.route("/dns/api/v1.0/")
@app.route("/dns/api/v1.0")
def v1():
    return "Welcome to the DNS/API v1.0"


@app.route("/")
def hello():
    return "Welcome to the DNS/API"


if __name__ == "__main__":
    app.run()
