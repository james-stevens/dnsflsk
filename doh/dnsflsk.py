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
import dns.message
import dns.resolver


class Empty:
    pass


def abort(err_no, message):
    if with_syslog:
        syslog.syslog(f'ERROR: #{err_no} {message}')
    response = flask.jsonify({'error': message})
    response.status_code = err_no
    return response


application = flask.Flask("DNS/Rest/api")

dohServers = "8.8.8.8,8.8.4.4"
if "DOH_SERVERS" in os.environ:
    dohServers = os.environ["DOH_SERVERS"]

with_syslog = True
if ("DOH_SYSLOG_SERVER" in os.environ
        and os.environ["DOH_SYSLOG_SERVER"] == "-"):
    with_syslog = False
else:
    syslogFacility = syslog.LOG_LOCAL6
    syslog.openlog(logoption=syslog.LOG_PID, facility=syslogFacility)


class Query:
    def __init__(self, req):
        self.name = None
        self.rdtype = None
        self.do = False
        self.cd = None
        self.ct = False
        self.servers = dohServers
        self.binary_format = False
        self.bin_data = None

        if req.content_type == "application/dns-message":
            self.queryFromLine(flask.request.get_data())
        elif len(req.form) > 0:
            self.queryFromJson(req.form)
        elif len(req.args) > 0:
            self.queryFromJson(req.args)

        self.servers = self.servers.split(",")
        self.servers = [resolv.resolv_host(s) for s in self.servers]

    def queryFromLine(self, bin_data):
        self.bin_data = bin_data
        self.binary_format = True
        msg = dns.message.from_wire(bin_data)

        rr = msg.question[0]
        self.name = rr.name.to_text()
        self.rdtype = rr.rdtype

        flags = [
            flag for flag in resolv.DNS_FLAGS
            if (msg.flags & resolv.DNS_FLAGS[flag])
        ]
        self.ct = "CT" in flags
        self.do = "DO" in flags
        self.cd = "CD" in flags

    def queryFromJson(self, sent_data):
        self.name = sent_data.get("name")
        self.rdtype = sent_data.get("type")

        self.servers = sent_data.get("servers", default=dohServers)
        self.ct = sent_data.get("ct", default=False, type=bool)
        self.cd = sent_data.get("cd", default=False, type=bool)
        self.do = sent_data.get("do", default=False, type=bool)

        if (not hasattr(self, "rdtype")) or self.rdtype is None:
            self.rdtype = 1
        elif self.rdtype.isdigit():
            self.rdtype = int(self.rdtype)
            if self.rdtype <= 0 or self.rdtype >= 65535:
                return abort(
                    400, f"'type' parameter is out of range ({self.rdtype})")
        else:
            try:
                self.rdtype = dns.rdatatype.from_text(self.rdtype)
            except (dns.rdatatype.UnknownRdatatype, ValueError) as e:
                return abort(400, "'type' parameter is not a known RR name")


@application.route('/resolv', methods=['GET', 'POST'])
@application.route('/dns/api/v1.0/resolv', methods=['GET', 'POST'])
def resolver():
    qry = Query(flask.request)

    for s in qry.servers:
        if not validation.is_valid_ipv4(s):
            return abort(400, "Bad server IPv4 Address")

    if qry.name is None:
        return abort(400, "'name' parameter is missing")

    if not validation.is_valid_host(qry.name):
        return abort(400, "'name' parameter is not a valid FQDN")

    try:
        if with_syslog:
            syslog.syslog("{}/{} -> {}".format(
                qry.name, dns.rdatatype.to_text(qry.rdtype), qry.servers))
        res = resolv.Resolver(qry)
    except Exception as e:
        return abort(400, e)

    rec = res.recv(qry.binary_format)
    if rec is None:
        return abort(400, "No valid answer received")

    if qry.binary_format:
        response = flask.make_response(qry.bin_data[:2] + rec[2:])
        response.headers.set('Content-Type', 'application/dns-message')
        return response
    else:
        return flask.jsonify(rec)


@application.route("/dns/api/v1.0/")
def v1():
    return "Welcome to the DNS/API v1.0"


@application.route("/")
def hello():
    return "Welcome to the DNS/API"


if __name__ == "__main__":
    application.run()
