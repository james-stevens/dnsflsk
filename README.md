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
response you get will be the first one received (as speciifed in the `Responder` property.


# Additional Properties

I've added in the property `Responder` into the JSON reply, with the IP Address of the server that responded.

It will also return the [flags](https://tools.ietf.org/html/rfc2065#section-6.1) `AA` and `QR`,
although `QR` must always be `True` as this is checked for in the code.

There is also the property `Flags` which is an array listing which flags are `True`.




# Running at Production Quality

I've also supplied all the extra files you'd need to run this at production quality. I used `gunicorn` and `nginx`.

* `pip install gunicorn` (if you don't already have it)
* Copy (or symlink) `nginx.conf` into the `${NGINX_BASE_DIR}/conf/dnsflsk.conf`
* Run `nginx -t -c conf/dnsflsk.conf` to check its OK
* Start Nginx with `nginx -c conf/dnsflsk.conf`
* Start WSGI/gunicorn with `./start_wsgi`

For `start_wsgi` to work, you may need to ensure `gunicorn` is in your run-path, or edit the script.

Now, from another ssh, you should be able to run something like

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
