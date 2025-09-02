# dnsflsk - [Docker.com - jamesstevens/doh](https://hub.docker.com/r/jamesstevens/doh)

This is a Rest/API DNS proxy following the [Google JSON/DNS/API](https://developers.google.com/speed/public-dns/docs/doh/json) spec,
AKA [DoH or DNS over HTTPS](https://developers.google.com/speed/public-dns/docs/doh/index).
Implemented using `Flask` and `dnspython` to do the heavy lifting.

It supports both the binary and JSON formats of DoH. To use the binary interface you *must* declare the `Content-type` as `application/dns-message`,
otherwise it will defaul to assuming you are using JSON.


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

You can also test out just the resolver code, using the command line utility `resolv.py`. The only required parameter is `-n <name>`.

```
usage: resolv.py [-h] [-s SERVERS] [-n NAME] [-c] [-d] [-T] [-t RDTYPE]

This is a wrapper to test the resolver code

options:
  -h, --help            show this help message and exit
  -s SERVERS, --servers SERVERS
                        Resolvers to query
  -n NAME, --name NAME  Name to query for
  -c, --cd              With DO bit, DNSSEC
  -d, --do              With DO bit, DNSSEC
  -T, --force-tcp       Force TCP query
  -t RDTYPE, --rdtype RDTYPE
                        RR Type to query for
```


# Running at Production Quality

For production use, I strongly recommend you simply use the container `jamesstevens / flask-doh`, or build the container yourself by running
`./dkmk`.

By default, the container will send its queries to the Google rsolvers `8.8.8.8` & `8.4.4.8`. By default
it will also run 3 forks which run 3 thread each. The forks are load-balanced using `nginx` and the threads 
are load balanced by `gunicorn`.

The number of threads and the destination DNS servers can be changed using the environment variables
`DOH_SESSIONS` and `DOH_SERVERS`, which can be specified at the command line (using `docker run -e`) or in a file
using `docket run --env-file=`.

`DOH_SERVERS` is a comma separated list of IP Addresses.

`DOH_SESSIONS` a positive integer for number fo `gunicorn` threads.

`nginx` will load-balance the forks, but doe not do any TLS/SSL - this must be doen externally. This

## Testing the container

If you build the container with `./dkmk`, then you should be able to run it with `./dkrun`. Once it is running this should work

	curl http://127.0.0.1/dns/api/v1.0/resolv?name=www.google.com

