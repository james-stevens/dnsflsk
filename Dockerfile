FROM alpine

RUN rmdir /tmp
RUN ln -s /dev/shm /tmp
RUN ln -s /dev/shm /ram

RUN apk add python3
RUN apk add py-pip
RUN apk add nginx

RUN pip install --upgrade pip
RUN pip install gunicorn
RUN pip install Flask
RUN pip install dnspython

COPY certkey.pem /etc/nginx/
RUN rm -f /etc/inittab
RUN ln -s /ram/inittab /etc/inittab
RUN ln -s /ram/nginx_ssl.conf /etc/nginx/nginx_ssl.conf

COPY *.py /opt/
COPY start_wsgi /opt/
COPY start_nginx /opt/
RUN python3 -m compileall /opt/

CMD [ /opt/start ]
