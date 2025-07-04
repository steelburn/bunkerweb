FROM nginx:1.28-alpine-slim@sha256:39a9a15e0a81914a96fa9ffa980cdfe08e2e5e73ae3424f341ad1f470147c413 AS builder

# Export var for specific actions on linux/arm/v7
ARG TARGETPLATFORM

# Install temporary requirements for the dependencies
RUN apk add --no-cache bash autoconf libtool automake geoip-dev g++ gcc curl-dev libxml2-dev pcre-dev make linux-headers musl-dev gd-dev gnupg brotli-dev openssl-dev patch readline-dev yajl yajl-dev yajl-tools py3-pip python3-dev libffi-dev postgresql-dev cargo

WORKDIR /tmp/bunkerweb/deps

# Copy dependencies sources folder
COPY src/deps/misc misc
COPY src/deps/src src
COPY src/deps/deps.json deps.json
COPY --chmod=644 src/deps/install.sh install.sh

# Compile and install dependencies
RUN bash install.sh

WORKDIR /tmp/crowdsec/deps

RUN apk add --no-cache jq git libc-dev gettext binutils-gold coreutils pkgconfig wget

COPY src/all-in-one/deps/go.json go.json
COPY --chmod=644 src/all-in-one/scripts/install-go.sh install-go.sh
COPY --chmod=644 src/all-in-one/scripts/utils.sh utils.sh

# Compile and install Go
RUN export PLATFORM="$(case "$TARGETPLATFORM" in \
    linux/amd64) echo "amd64" ;; \
    linux/arm64) echo "arm64" ;; \
    linux/arm/v7) echo "armv6l" ;; \
    linux/386) echo "386" ;; \
    *) echo "amd64" ;; \
    esac)" && \
    export VERSION="$(jq -r .version go.json)" && \
    export URL="$(jq -r .url go.json | sed "s/{VERSION}/$VERSION/" | sed "s/{PLATFORM}/$PLATFORM/")" && \
    export SHA256="$(if [ "$PLATFORM" = "386" ]; then jq -r '.checksums."386"' go.json; else jq -r ".checksums.$PLATFORM" go.json; fi)" && \
    bash install-go.sh

COPY src/all-in-one/deps/re2.json re2.json
COPY --chmod=644 src/all-in-one/scripts/install-re2.sh install-re2.sh

# Compile and install re2
RUN export MAKEFLAGS="-j$(nproc)" && \
    export GOMAXPROCS="-j$(nproc)" && \
    export PATH="/usr/local/go/bin:$PATH" && \
    export VERSION="$(jq -r .version re2.json)" && \
    export URL="$(jq -r .url re2.json)" && \
    export COMMIT="$(jq -r .commit re2.json)" && \
    bash install-re2.sh && \
    go install github.com/mikefarah/yq/v4@v4.44.3

COPY src/all-in-one/deps/crowdsec.json crowdsec.json
COPY --chmod=644 src/all-in-one/scripts/install-crowdsec.sh install-crowdsec.sh

# Compile and install crowdsec
RUN export GOMAXPROCS="-j$(nproc)" && \
    export PATH="/usr/local/go/bin:$PATH" && \
    export VERSION="$(jq -r .version crowdsec.json)" && \
    export URL="$(jq -r .url crowdsec.json)" && \
    export COMMIT="$(jq -r .commit crowdsec.json)" && \
    bash install-crowdsec.sh

WORKDIR /usr/share/bunkerweb

RUN mv /tmp/crowdsec/deps/crowdsec/crowdsec-release.tgz .

# Copy python requirements
COPY src/deps/requirements.txt /tmp/requirements-deps.txt
COPY src/autoconf/requirements.txt /tmp/req/requirements-autoconf.txt
COPY src/scheduler/requirements.txt /tmp/req/requirements-scheduler.txt
COPY src/ui/requirements.txt /tmp/req/requirements-ui.txt
COPY src/common/gen/requirements.txt /tmp/req/requirements-gen.txt
COPY src/common/db/requirements.txt /tmp/req/requirements-db.txt
COPY src/common/db/requirements.armv7.txt /tmp/req/requirements-db.armv7.txt

# Install python requirements
RUN export MAKEFLAGS="-j$(nproc)" && \
    if [ "$TARGETPLATFORM" = "linux/arm/v7" ] ; then mv /tmp/req/requirements-db.armv7.txt /tmp/req/requirements-db.txt ; else rm -f /tmp/req/requirements-db.armv7.txt ; fi && \
    pip install --no-cache-dir --require-hashes --break-system-packages -r /tmp/requirements-deps.txt && \
    pip install --no-cache-dir --require-hashes --target deps/python $(for file in $(ls /tmp/req/requirements*.txt) ; do echo "-r ${file}" ; done | xargs)

# Copy files
COPY src/bw/entrypoint.sh entrypoint.sh
COPY src/bw/loading loading
COPY src/bw/lua lua
COPY src/bw/misc misc
COPY src/common/api api
COPY src/common/cli cli
COPY src/common/confs confs
COPY src/common/db db
COPY src/common/core core
COPY src/common/gen gen
COPY src/common/helpers helpers
COPY src/common/settings.json settings.json
COPY src/common/utils utils
COPY src/autoconf autoconf
COPY src/scheduler scheduler
COPY src/ui ui
COPY src/all-in-one all-in-one
COPY src/VERSION VERSION
COPY misc/*.ascii misc/

# Minify JS files (can be skipped with SKIP_MINIFY=yes)
ARG SKIP_MINIFY=no
RUN if [ "$SKIP_MINIFY" != "yes" ]; then \
    apk add --no-cache nodejs npm parallel && \
    npm install -g uglify-js && \
    find ui/app/static -type f -name "*.js" | parallel 'uglifyjs {} --compress --mangle --verbose --output {}' ; \
    else \
    echo "Skipping JS minification"; \
    fi

FROM nginx:1.28-alpine-slim@sha256:39a9a15e0a81914a96fa9ffa980cdfe08e2e5e73ae3424f341ad1f470147c413

# Set default umask to prevent huge recursive chmod increasing the final image size
RUN umask 027

# Install runtime dependencies including supervisord
RUN apk add --no-cache bash curl geoip grep libgcc libgd libmagic libpq libstdc++ libxml2 mariadb-client mariadb-connector-c openssl pcre postgresql-client python3 py3-pip sed sqlite tzdata unzip yajl supervisor

# Fix CVEs
RUN apk add --no-cache "pyc>=3.12.11-r0" "python3>=3.12.11-r0" "python3-pyc>=3.12.11-r0" "python3-pycache-pyc0>=3.12.11-r0" # CVE-2024-12718 CVE-2025-4138 CVE-2025-4517 CVE-2025-4330

COPY src/deps/requirements.txt /tmp/requirements-deps.txt

# Install updated python requirements to fix CVEs
RUN export MAKEFLAGS="-j$(nproc)" && \
    pip install --no-cache-dir --require-hashes --break-system-packages -r /tmp/requirements-deps.txt && \
    rm -f /tmp/requirements-deps.txt

# Copy dependencies
COPY --from=builder --chown=0:101 --chmod=550 /usr/share/bunkerweb /usr/share/bunkerweb

WORKDIR /usr/share/bunkerweb

# Move bwcli, create data folders and set permissions
RUN cp helpers/bwcli /usr/bin/ && \
    echo "Docker" > INTEGRATION && \
	mkdir -p /etc/bunkerweb /var/tmp/bunkerweb /var/run/bunkerweb /var/log/bunkerweb /var/www && \
	mkdir -p /data/cache && ln -s /data/cache /var/cache/bunkerweb && \
	mkdir -p /data/lib && ln -s /data/lib /var/lib/bunkerweb && \
	mkdir -p /data/www && ln -s /data/www /var/www/html && \
	for dir in $(echo "pro configs plugins") ; do mkdir -p "/data/${dir}" && ln -s "/data/${dir}" "/etc/bunkerweb/${dir}" ; done && \
	for dir in $(echo "pro/plugins configs/http configs/stream configs/server-http configs/server-stream configs/default-server-http configs/default-server-stream configs/modsec configs/modsec-crs configs/crs-plugins-before configs/crs-plugins-after") ; do mkdir "/data/${dir}" ; done && \
	chown -R root:nginx INTEGRATION /data /etc/nginx /var/cache/bunkerweb /var/lib/bunkerweb /var/www/html /etc/bunkerweb /var/tmp/bunkerweb /var/run/bunkerweb /var/log/bunkerweb /usr/bin/bwcli && \
	chmod -R 770 /data /etc/nginx /var/cache/bunkerweb /var/lib/bunkerweb /var/www/html /etc/bunkerweb /var/tmp/bunkerweb /var/log/bunkerweb /var/run/bunkerweb && \
    find . \( -path './all-in-one' -o -path './scheduler' -o -path './ui' -o -path './autoconf' -o -path './cli' -o -path './lua' -o -path './core' -o -path './db' -o -path './gen' -o -path './helpers' -o -path './deps' \) -prune -o -type f -print0 | xargs -0 -P "$(nproc)" -n 1024 chmod 440 && \
    find all-in-one scheduler ui autoconf cli lua core db gen helpers deps -type f ! -path 'deps/bin/*' ! -path 'deps/python/bin/*' ! -name '*.lua' ! -name '*.py' ! -name '*.pyc' ! -name '*.sh' ! -name '*.so' -print0 | xargs -0 -P "$(nproc)" -n 1024 chmod 440 && \
    chmod 770 -R db/alembic && \
    chmod 550 entrypoint.sh && \
    chmod 660 INTEGRATION && \
    mkdir -p /var/log/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    chmod -R 755 /var/log/nginx && \
    rm -rf /var/log/bunkerweb/* && \
    # Setup CrowdSec
    tar -xzf crowdsec-release.tgz && \
    mkdir /data/crowdsec && ln -s /data/crowdsec /var/lib/crowdsec && \
    cd crowdsec-v* && \
    ./wizard.sh --docker-mode && \
    cd .. && \
    mv all-in-one/conf/config.yaml /etc/crowdsec/config.yaml && \
    mv all-in-one/conf/acquis.yaml /etc/crowdsec/acquis.yaml && \
    mv all-in-one/conf/appsec.yaml /etc/crowdsec/acquis.d/appsec.yaml && \
    rm -rf crowdsec* all-in-one/deps all-in-one/scripts && \
    chown -R root:nginx /data /var/lib/crowdsec /etc/crowdsec /usr/local/lib/crowdsec && \
	chmod -R 770 /data /var/lib/bunkerweb /etc/crowdsec /usr/local/lib/crowdsec && \
    find /etc/crowdsec/ -type f -name "*.yaml" -print0 | xargs -0 chmod 660 && \
    mv /etc/crowdsec/online_api_credentials.yaml /var/lib/crowdsec/online_api_credentials.yaml && \
    mv /etc/crowdsec/local_api_credentials.yaml /var/lib/crowdsec/local_api_credentials.yaml && \
    # Setup Redis && \
    mkdir /data/redis && ln -s /data/redis /var/lib/redis && \
    apk add --no-cache redis && \
    mv all-in-one/conf/redis.conf /etc/redis.conf && \
    rm -rf all-in-one/conf && \
    chown -R root:nginx /data /var/lib/redis /etc/redis.conf && \
    chmod -R 770 /data /var/lib/redis && \
    chmod 660 /etc/redis.conf && \
    # Set up supervisor configuration && \
    mv /usr/share/bunkerweb/all-in-one/supervisord.conf /etc/supervisord.conf && \
    mv /usr/share/bunkerweb/all-in-one/supervisor.d /etc/supervisor.d && \
    chmod 770 -R /etc/supervisor.d

COPY --chown=root:nginx --chmod=770 src/bw/misc/asn.mmdb /var/tmp/bunkerweb/asn.mmdb
COPY --chown=root:nginx --chmod=770 src/bw/misc/country.mmdb /var/tmp/bunkerweb/country.mmdb

LABEL maintainer="Bunkerity <contact@bunkerity.com>"
LABEL version="1.6.1"
LABEL url="https://www.bunkerweb.io"
LABEL bunkerweb.type="all-in-one"
LABEL bunkerweb.INSTANCE="bunkerweb"

VOLUME /data

EXPOSE 8080/tcp 8443/tcp 8443/udp 7000/tcp

HEALTHCHECK --interval=10s --timeout=10s --start-period=30s --retries=6 CMD /usr/share/bunkerweb/helpers/healthcheck-all-in-one.sh

ENV PYTHONPATH="/usr/share/bunkerweb/deps/python:/usr/share/bunkerweb/db"
ENV SERVICE_UI="yes"
ENV SERVICE_SCHEDULER="yes"
ENV AUTOCONF_MODE="no"
ENV USE_CROWDSEC="no"
ENV USE_REDIS="yes"

USER nginx:nginx

ENTRYPOINT ["/usr/share/bunkerweb/all-in-one/entrypoint.sh"]
