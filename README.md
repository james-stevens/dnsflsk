# dnsflsk - [Docker.com - jamesstevens/doh](https://hub.docker.com/r/jamesstevens/doh)

This is a Rest/API DNS proxy following the [Google JSON/DNS/API](https://developers.google.com/speed/public-dns/docs/doh/json) spec,
AKA [DoH or DNS over HTTPS](https://developers.google.com/speed/public-dns/docs/doh/index).  Implemented using `Flask` and `dnspython` to do the heavy lifting.

Google also supports sending binary DNS query packets to their service. This does not.

It allows you to issue JSON DNS queries and get JSON responses, with the DNS done using an 
underlying UDP client socket.  It really should be ASGI, but its currently WSGI.



# Additional Options

In addition to the [Google Supported Parameters](https://developers.google.com/speed/public-dns/docs/doh/json#supported_parameters)
, this API also supports the parameter `servers` as a comma separated list of DNS servers you want your query sent to.
Each server can be specified as either a name or IPv4 address. Names will be resolved using your server's default resolution mechanism
(i.e. the same as the command line).

If you do not specify a `servers` option, it will default to `8.8.8.8,8.8.4.4` (Google). If you 
set the environment variable `DOH_SERVERS` as a comma separated list of IP Addresses, this will be used instead.

When more than one server is specified, your query will be sent to all the `servers`, and the
response you get will be the first one received, as specified in the `Responder` property.


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

For production use, I strongly recommend you simply use the container `jamesstevens / doh`, or build the container yourself by running
`./dkmk`.

By default, the container will send its queries to the Google rsolvers `8.8.8.8` & `8.4.4.8`. By default
it will also run 5 `python/gunicorn` threads and load-balance them using `nginx`.

The number of sessions and the destination DNS servers can be changed using the environment variables
`DOH_SESSIONS` and `DOH_SERVERS`, which can be specified at the command line (using `docker run -e`) or in a file
using `docket run --env-file=`.

`DOH_SERVERS` is a comma separated list of IP Addresses.

`DOH_SESSIONS` is simply a positive integer.

`nginx` will also do the SSL using the key & certificate in the file `certkey.pem`, which has been created using a private
certificate authority. The public key for this private CA is in the file `myCA.pem`.

The server name for the key is `doh.jrcs.net` which should resolve to `127.0.0.1`, so if you start the container with `./dkrun`, then run

	curl --cacert myCA.pem https://doh.jrcs.net:800/dns/api/v1.0/resolv?name=www.google.com

then it should work fine, but for production use I would recommend you replace the certificate with a publicly verifiable one.

NOTE: the container is designed to run `read-only` so we would recommend you use this. e.g.

	docker run --read-only -it -p 800:800 doh
