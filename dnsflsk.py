#! /usr/bin/python3

import resolv

import flask
import dns
import dns.rdatatype
import dns.resolver
import re

is_valid_host_re = re.compile(r'^([0-9a-z][-\w]*[0-9a-z]\.)+[a-z0-9\-]{2,15}$')


def is_valid_host(host):
    return is_valid_host_re.match(host) is not None


def abort(err_no, message):
    response = flask.jsonify({'error': message})
    response.status_code = err_no
    return response


application = flask.Flask("DNS/Rest/api")


@application.route('/dns/api/v1.0/resolv', methods=['GET'])
def resolver():
    qry = {}
    qry["name"] = flask.request.args.get("name")
    qry["type"] = flask.request.args.get("type")
    qry["servers"] = flask.request.args.get("servers",
                                            default="192.168.1.20").split(",")
    qry["ct"] = flask.request.args.get("ct", default=False, type=bool)
    qry["cd"] = flask.request.args.get("cd")
    qry["do"] = flask.request.args.get("do", default=False, type=bool)

    if "name" not in qry:
        return abort(400, "'name' parameter is missing")

    if not is_valid_host(qry["name"]):
        return abort(400, "'name' parameter is not a valid FQDN")

    if "type" not in qry or qry["type"] is None:
        qry["type"] = 1
    elif qry["type"].isdigit():
        qry["type"] = int(qry["type"])
        if qry["type"] <= 0 or qry["type"] >= 65535:
            return abort(400, "'type' parameter is out of range")
    else:
        try:
            qry["type"] = dns.rdatatype.from_text(qry["type"])
        except (dns.rdatatype.UnknownRdatatype, ValueError) as e:
            return abort(400, "'type' parameter is not a known RR name")

    answer = resolv.Resolver(qry)
    rec = answer.recv()
    if rec is None:
        return abort(400, "No valid answer received")

    return flask.jsonify(rec)


@application.route("/dns/api/v1.0/")
@application.route("/dns/api/v1.0")
def v1():
    return "Welcome to the DNS/API v1.0"


@application.route("/")
def hello():
    return "Welcome to the DNS/API"


if __name__ == "__main__":
    application.run()
