# dnsflsk

This is a Rest/API DNS proxy following the [Google JSON/DNS/API](https://developers.google.com/speed/public-dns/docs/doh/json) spec,
AKA [DoH or DNS over HTTPS](https://developers.google.com/speed/public-dns/docs/doh/index).  Implemented using `Flask` and `dnspython` to do the heavy lifting.

Google also supports sending binary DNS query packets to their service. This does not.

It allows you to issue JSON DNS queries and get JSON responses, with the DNS done using an 
underlying UDP client socket.  It really should be ASGI, but its currently WSGI.

I've used ...

* Python - v3.6.9
* dnspython - v1.16.0 (`pip install dnspython`)
* Flask - v1.1.1 (`pip install Flask`)

Installing `nginx` or `Python` needs to be done using your O/S level install procedure.

But it doesn't do anything tricky, so any reasonably recent version will probably work.

If you feel like it, leave a comment in the [first issue](https://github.com/james-stevens/dnsflsk/issues/1) called `Just for chatting`


# Status

The code works, but I'll probably keep updating it, if I can think of anything else, or in response to feedback / bugs.


# Additional Options

In addition to the [Google Supported Parameters](https://developers.google.com/speed/public-dns/docs/doh/json#supported_parameters)
, this API also supports the parameter `servers` as a comma separated list of DNS servers you want your query sent to.
Each server can be specified as either a name or IPv4 address. Names will be resolved using your server's default resolution mechanism
(i.e. the same as the command line).

If you do not specify a `servers` option, it will default to `8.8.8.8,8.8.4.4` (Google).

When more than one server is specified, your query will be sent to all the `servers`, and the
response you get will be the first one received (as specified in the `Responder` property.


# Additional Properties

I've added in the property `Responder` into the JSON reply, with the IP Address of the server that responded.

It will also return the [flags](https://tools.ietf.org/html/rfc2065#section-6.1) `AA` and `QR`,
although `QR` must always be `True` as this is checked for in the code.

There is also the property `Flags` which is an array listing which flags are `True`.


# Testing it Out

You can run it in the basic `Flask` HTTP server, but running `./dnsflsk.py` and it will answer queries on `http://127.0.0.1:5000`

e.g.
```
$ curl 'http://127.0.0.1:5000/dns/api/v1.0/resolv?name=www.google.com'
```

Note: This form of execution is not suitable for production use, see below.

You can also test out just the resolver code, using the command line utility `cmdresolv.py`. The only required parameter is `-n <name>`.

```
usage: cmdresolv.py [-h] [-s SERVERS] [-t RDTYPE] [-n NAME] [-d] [-c]

Process some integers.

optional arguments:
  -h, --help            show this help message and exit
  -s SERVERS, --servers SERVERS
                        Comma separated list of server ip addresses
  -t RDTYPE, --rdtype RDTYPE
                        Record type to query (number or name), default=A
  -n NAME, --name NAME  Name to look-up
  -d, --do              Set DO bit
  -c, --cd              Same as --do

```


# Running at Production Quality

I've also supplied all the extra files you'd need to run this at production quality. I used `gunicorn` and `nginx`.

* `pip install gunicorn` (if you don't already have it)
* Copy (or symlink) `nginx.conf` into the `${NGINX_BASE_DIR}/conf/dnsflsk.conf`
* Run `nginx -t -c conf/dnsflsk.conf` to check its OK
* Start Nginx with `nginx -c conf/dnsflsk.conf`
* Start WSGI/gunicorn with `./start_wsgi`

For `start_wsgi` to work, you may need to ensure `gunicorn` is in your run-path, or edit the script.

Then, from another ssh, you should be able to run something like

```
$ curl 'http://127.0.0.1:800/dns/api/v1.0/resolv?name=www.google.com'
```
If you fail to start the WSGI agent, you will get an HTTP `502 Bad Gateway` message

If it works, you'll see something like this
```
$ curl 'http://127.0.0.1:800/dns/api/v1.0/resolv?name=www.google.com' 2>/dev/null | jq
{
  "QR": true,
  "AA": false,
  "TC": false,
  "RD": true,
  "CD": false,
  "AD": false,
  "RA": true,
  "Flags": [
    "QR",
    "RD",
    "RA"
  ],
  "Status": 0,
  "Question": [
    {
      "name": "www.google.com.",
      "type": 1
    }
  ],
  "Answer": [
    {
      "name": "www.google.com.",
      "data": "216.58.210.36",
      "type": 1
    }
  ],
  "Authority": [],
  "Responder": "8.8.4.4"
}
```


# Runnning in a Production Docker Container

I've created a base container image called [`jamesstevens/mini-slack142-py38-nginx`](https://hub.docker.com/repository/docker/jamesstevens/jamesstevens/mini-slack142-py38-nginx)
that has `nginx` and `Python` in it, and then created an application container to run `dnsflsk` in that.

All you need to do is

* Have a current `docker` platform :)
* Run `docker pull jamesstevens/mini-slack142-py38-nginx:vX.X` (where X.X is the latest version) to get the base container (optional)
* Run `./dkmk` to build the application container (must be run in a directory containing a clone of this project)
* Run `./dkrun init` to run it, you can also use `./dkrun sh` to shell into the container.

This will run `dnsflsk` (under `gunicorn`) and `nginx` under the very basic, but still very good, supervisor program `sysvinit`

You should get some commentary like this...
```
INIT: version 2.89 booting
INIT: Entering runlevel: 3
[2020-01-17 16:27:34 +0000] [8] [INFO] Starting gunicorn 20.0.4
[2020-01-17 16:27:34 +0000] [8] [INFO] Listening at: unix:/var/run/dnsflsk.sock (8)
[2020-01-17 16:27:34 +0000] [8] [INFO] Using worker: sync
[2020-01-17 16:27:34 +0000] [13] [INFO] Booting worker with pid: 13
```

Then, once again, a command like this should test it works
```
$ curl 'http://127.0.0.1:800/dns/api/v1.0/resolv?name=www.google.com'
```

You can also test the container by running `/bin/sh` instead, then running `/app/cmdresolv.py -n www.google.com` from the container's shell.
You can, of course, also (instead) invoke `cmdresolv.py` directly from a `docker run` command.

I've provided the one-line shell scripts `dkmk` to build the app container and `dkrun <cmd>` to run the container, where `<cmd>` will
probably be either `sh` to get a shell in the container or `init` to run `sysvinit` to start the application.

If you want to run `nginx` in the container as an `HTTPS` instead of an `HTTP` server, then all you need to do is copy a file called `cert.pem` into this 
directory **before** you build the container. The file will then be copied into the `nginx/conf` directory and used by the `start_nginx` script.

The `cert.pem` file must contain **both** the private key and the certificate. For example ...
```
cat /opt/daemon/keys/letsencrypt/cert.pem /opt/daemon/keys/letsencrypt/privkey.pem > cert.pem
```
