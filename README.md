# dnsflsk
This is an HTTPS/JSON <-> DNS proxy following the [Google JSON/DNS/API](https://developers.google.com/speed/public-dns/docs/doh/json),
using `Flask` and `dnspython` to do the heavy lifting.

I'm using ...

* Python - v3.6.9
* dnspython - v1.16.0
* Flask - v1.1.1

It's mostly just for fun, but if you find it useful - cool.

If you feel like it, leave a comment in the [first issue](https://github.com/james-stevens/dnsflsk/issues/1) called `Just for chatting`



# Additional Option

In addition to the [Google Supported Parameters](https://developers.google.com/speed/public-dns/docs/doh/json#supported_parameters)
, this API also supports the paramter `servers` as a comma separated list of DNS servers you want your query sent to.

And I've addded in the attribute `Responder` into the JSON reply, with the IP Address of the server that responded.

If you do not specify a `servers` option, it will default to `8.8.8.8,8.8.4.4` (Google).

When more than one server is specified, your query will be sent to all the `servers`, and the
response you get will be the first one received.


# Status

The code works, but could do with a lot of additional work to make it more defensive.



# Running at Production Quality

To run this at production quality, I used `gunicorn` and `nginx`.

* `pip install gunicorn` (if you don't already have it)
* Copy (or symlink) `nginx.conf` into the `${NGINX_BASE_DIR}/conf/dnsflsk.conf`
* Run `nginx -t -c conf/dnsflsk.conf` to check its OK
* Start Nginx with `nginx -c conf/dnsflsk.conf`
* Start WSGI/gunicorn with `./start_wsgi`

For `start_wsgi` to work, you may need to ensure `gunicorn` is in your run-path, or edit the script.

Now, from another ssh, you should be able to run something like

```
$ curl 'http://127.0.0.1:800/dns/api/v1.0/resolv?name=www.google.com&type=1&servers=8.8.4.4'
```
If you fail to start the WSGI agent, you will get an HTTP `502 Bad Gateway` message

If it works, you'll see something like this
```
$ curl 'http://127.0.0.1:800/dns/api/v1.0/resolv?name=www.google.com&type=1&servers=8.8.4.4' 2>/dev/null | jq
{
  "AD": false,
  "Answer": [
    {
      "data": "216.58.206.100",
      "name": "www.google.com.",
      "type": 1
    }
  ],
  "Authority": [],
  "CD": false,
  "Question": [
    {
      "name": "www.google.com.",
      "type": 1
    }
  ],
  "RA": true,
  "RD": true,
  "Status": 0,
  "TC": false
}
```
