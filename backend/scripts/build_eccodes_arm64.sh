#!/bin/bash
set -e

if [ "$TARGETOS" != "linux" ] || [ "$TARGETARCH" != "arm64" ]; then
  echo "Skipping eccodes build on $TARGETOS/$TARGETARCH (using Python eccodeslib package)"
  exit 0
fi

echo "Linux ARM64 detected: Building eccodes 2.42.0 from source..."

# install build dependencies
apt-get update
apt-get install -y --no-install-recommends \
  build-essential \
  cmake \
  gfortran \
  libaec-dev \
  libnetcdf-dev \
  wget \
  ca-certificates

# download and extract
cd /tmp
wget -q https://confluence.ecmwf.int/download/attachments/45757960/eccodes-2.42.0-Source.tar.gz
tar -xzf eccodes-2.42.0-Source.tar.gz

# configure
# https://confluence.ecmwf.int/display/ECC/ecCodes+installation#ecCodesinstallation-Overview
mkdir eccodes-build && cd eccodes-build
cmake \
  -DCMAKE_INSTALL_PREFIX=/usr/local \
  -DENABLE_NETCDF=OFF \
  -DENABLE_FORTRAN=OFF \
  ../eccodes-2.42.0-Source

# build and install
make -j$(nproc)
make install

# cleanup
cd /
rm -rf /tmp/eccodes*
apt-get remove -y build-essential cmake wget
apt-get autoremove -y
rm -rf /var/lib/apt/lists/*

echo "eccodes successfully built and installed to /usr/local"
