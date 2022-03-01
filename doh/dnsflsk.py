#! /usr/bin/python3
# (c) Copyright 2019-2020, James Stevens ... see LICENSE for details
# Alternative license arrangements possible, contact me for more information

import resolv
import validation
import os
import syslog

import flask
import dns
import dns.rdatatype
import dns.resolver


class Empty:
    pass


def abort(err_no, message):
    response = flask.jsonify({'error': message})
    response.status_code = err_no
    return response


application = flask.Flask("DNS/Rest/api")

dohServers = "8.8.8.8,8.8.4.4"
if "DOH_SERVERS" in os.environ:
    dohServers = os.environ["DOH_SERVERS"]

syslogFacility = syslog.LOG_LOCAL6
syslog.openlog(logoption=syslog.LOG_PID, facility=syslogFacility)


@application.route('/dns/api/v1.0/resolv', methods=['GET'])
def resolver():
    qry = Empty()
    qry.name = flask.request.args.get("name")
    qry.rdtype = flask.request.args.get("type")

    qry.servers = flask.request.args.get("servers", default=dohServers)
    qry.ct = flask.request.args.get("ct", default=False, type=bool)
    qry.cd = flask.request.args.get("cd")
    qry.do = flask.request.args.get("do", default=False, type=bool)

    qry.servers = qry.servers.split(",")
    qry.servers = [resolv.resolv_host(s) for s in qry.servers]

    for s in qry.servers:
        if not validation.is_valid_ipv4(s):
            return abort(400, "Bad server IPv4 Address")

    if not hasattr(qry, "name"):
        return abort(400, "'name' parameter is missing")

    if not validation.is_valid_host(qry.name):
        return abort(400, "'name' parameter is not a valid FQDN")

    if (not hasattr(qry, "rdtype")) or qry.rdtype is None:
        qry.rdtype = 1
    elif qry.rdtype.isdigit():
        qry.rdtype = int(qry.rdtype)
        if qry.rdtype <= 0 or qry.rdtype >= 65535:
            return abort(400, "'type' parameter is out of range")
    else:
        try:
            qry.rdtype = dns.rdatatype.from_text(qry.rdtype)
        except (dns.rdatatype.UnknownRdatatype, ValueError) as e:
            return abort(400, "'type' parameter is not a known RR name")

    try:
        syslog.syslog("{}/{} -> {}".format(qry.name, dns.rdatatype.to_text(qry.rdtype), qry.servers))
        res = resolv.Resolver(qry)
    except Exception as e:
        return abort(400, e)

    rec = res.recv()
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
