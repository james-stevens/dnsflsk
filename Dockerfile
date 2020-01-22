FROM jamesstevens/mini-slack142-py38-nginx:v1.3

COPY *.py /app/
COPY start_wsgi /app/
COPY start_nginx /app/
COPY nginx_dnsflsk.conf nginx_dnsflsk_ssl.conf cert.* /usr/local/nginx/conf/
COPY inittab /etc/inittab

RUN pip install --upgrade pip
RUN pip install gunicorn
RUN pip install Flask
RUN pip install dnspython
RUN python -m compileall /app/
