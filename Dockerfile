FROM jamesstevens/mini-slack142-py38-nginx:v1.0

COPY *.py /app/
COPY start_wsgi /app/
COPY start_nginx /app/
COPY nginx.conf /usr/local/nginx/conf/dnsflsk.conf
COPY inittab /etc/inittab

RUN pip install --upgrade pip
RUN pip install gunicorn
RUN pip install Flask
RUN pip install dnspython
RUN python -m compileall /app/
