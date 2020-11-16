FROM padhi/portfolio-chc-solver:builder AS builder


COPY --chown=user:user freqhorn  /home/user/freqhorn
COPY --chown=user:user freqn     /home/user/freqn
COPY --chown=user:user lig-chc   /home/user/lig-chc
COPY --chown=user:user z3-spacer /home/user/z3-spacer
COPY --chown=user:user patches   /home/user/patches


ARG MAKEFLAGS="-j8"

RUN cd freqhorn \
 && ( [ ! -f "../patches/freqhorn.patch" ] || \
      patch -p0 < ../patches/freqhorn.patch) \
 && mkdir build \
 && cd build \
 && export PYTHON=python3 \
 && export CC=gcc-4.9 \
 && export CXX=g++-4.9 \
 && cmake .. \
 && make \
 && make

RUN cd freqn \
 && ( [ ! -f "../patches/freqn.patch" ] || \
      patch -p0 < ../patches/freqn.patch) \
 && mkdir build \
 && cd build \
 && cp -r ../../freqhorn/build/run . \
 && export PYTHON=python3 \
 && export CC=gcc-4.9 \
 && export CXX=g++-4.9 \
 && cmake .. \
 # Do NOT remove this second `cmake ..`!
 # For whatever reason, this is needed to "recognize" the run/ dir.
 && cmake .. \
 && make \
 && make

RUN cd z3-spacer \
 && ( [ ! -f "../patches/z3-spacer.patch" ] || \
      patch -p0 < ../patches/z3-spacer.patch) \
 && mkdir build \
 && python3 scripts/mk_make.py --staticbin --staticlib --build build \
 && cd build \
 && make

RUN cd lig-chc \
 && ( [ ! -f "../patches/lig-chc.patch" ] || \
      patch -p0 < ../patches/lig-chc.patch) \
 && eval "$(opam env)" \
 && opam exec -- dune build @NoLog \
 && opam exec -- dune build




FROM debian:buster-slim

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get upgrade -yq \
 && apt-get install -yq \
            curl \
            libatomic1 libgomp1 \
            procps python3 python3-pip \
            vim \
 && apt-get autoclean \
 && apt-get autoremove -y --purge \
 && python3 -m pip install pyparsing \
 && adduser --disabled-password \
            --home /home/user \
            --shell /bin/bash \
            --gecos '' user \
 && mkdir -p /home/user/solver/translators \
 && chown -R user:user /home/user


COPY --chown=user:user \
     engines \
     /home/user/solver/engines

COPY --chown=user:user \
     processors \
     /home/user/solver/processors

COPY --from=builder \
     --chown=user:user \
     /home/user/z3-spacer/build/z3 \
     /home/user/solver/engines/z3-spacer/z3

COPY --from=builder \
     --chown=user:user \
     /home/user/freqhorn/build/tools/deep/freqhorn \
     /home/user/solver/engines/freqhorn/freqhorn

COPY --from=builder \
     --chown=user:user \
     /home/user/freqn/build/tools/nonlin/freqn \
     /home/user/solver/engines/freqn/freqn

COPY --from=builder \
     --chown=user:user \
     /home/user/lig-chc/_build \
     /home/user/solver/engines/lig-chc_build
COPY --from=builder \
     --chown=user:user \
     /home/user/lig-chc/loopinvgen.sh \
     /home/user/solver/engines/lig-chc.sh


USER user
WORKDIR /home/user/solver


RUN mkdir tmp \
 && rm -rf engines/__pycache_ engines/*/__pycache_ \
 && mkdir -p engines/lig-chc/_dep \
 && cd engines/lig-chc \
 && ln -s ../../z3-spacer/z3 _dep/z3 \
 && cp -L ../lig-chc_build/install/default/bin/* . \
 && rm -rf ../lig-chc_build \
 && mv ../lig-chc.sh . \
 && sed -i 's#^BIN_DIR=.*$#BIN_DIR="$SELF_DIR"#' lig-chc.sh


COPY --chown=user:user \
     SyGuS-Org_tools/work-in-progress/chc-comp/to-sygus.py \
     /home/user/solver/translators/smt-to-sygus.py

COPY --chown=user:user \
     SyGuS-Org_tools/work-in-progress/chc-comp/from-sygus.py \
     /home/user/solver/translators/sygus-to-smt.py

COPY --chown=user:user \
     solver.py \
     /home/user/solver/solver.py


ENTRYPOINT [ "python3" , "solver.py" ]
