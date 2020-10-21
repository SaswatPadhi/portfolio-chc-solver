FROM debian:buster-slim


ARG OPAM_VERSION=2.0.7
ARG OCAML_VERSION=4.11.1+flambda


ARG DEBIAN_FRONTEND=noninteractive
RUN echo "deb http://deb.debian.org/debian/ jessie main contrib non-free" >> /etc/apt/sources.list \
 && apt-get update \
 && apt-get upgrade -yq \
 && apt-get install -yq \
            build-essential \
            cmake curl \
            g++-4.9 git \
            libboost-dev libboost-system-dev libgmp-dev libgomp1 libomp5 libomp-dev \
            m4 \
            python3 python3-setuptools \
            subversion \
            time tzdata \
            unzip \
            vim \
 && apt-get autoclean \
 && apt-get autoremove -y --purge \
 && adduser --disabled-password \
            --home /home/user \
            --shell /bin/bash \
            --gecos '' user \
 && curl -Lo /usr/local/bin/opam \
         "https://github.com/ocaml/opam/releases/download/$OPAM_VERSION/opam-$OPAM_VERSION-$(uname -m)-$(uname -s)" \
 && chmod 755 /usr/local/bin/opam


USER user
WORKDIR /home/user


RUN opam init --auto-setup \
              --disable-sandboxing \
              --yes \
              --compiler=$OCAML_VERSION \
              --enable-shell-hook \
              --dot-profile=~/.bashrc \
 && opam clean \
 && eval "$(opam env)" \
 && opam install --yes \
         bignum.v0.14.0 \
         bitv.1.4 \
         core.v0.14.0 \
         alcotest.1.2.3 \
         dune.2.7.1
