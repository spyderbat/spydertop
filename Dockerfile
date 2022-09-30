FROM python:3-alpine as build

RUN apk add --no-cache git

# install limited asciimatics
# this is necessary to remove the pillow dependency
# see https://github.com/peterbrittain/asciimatics/issues/95
WORKDIR /
RUN git clone https://github.com/peterbrittain/asciimatics.git && \
    cd asciimatics && \
    rm asciimatics/renderers/images.py && \
    grep -v 'Pillow >= [0-9]*\.[0-9]*\.[0-9]*' setup.py > setup.py.tmp && \
    mv setup.py.tmp setup.py && \
    python setup.py bdist_wheel

# install spydertop
WORKDIR /spydertop
COPY ./ ./
RUN pip wheel . -w dist --no-deps

FROM python:3-alpine

WORKDIR /spydertop
COPY --from=build /asciimatics/dist/asciimatics-*.whl ./
RUN pip --no-cache-dir install asciimatics-*.whl
COPY --from=build /spydertop/dist/spydertop-*.whl ./
RUN pip --no-cache-dir install spydertop-*.whl

COPY ./examples /spydertop/examples

VOLUME /root/.spyderbat-api

# run the app
ENTRYPOINT ["spydertop"]
