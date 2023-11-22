#!/bin/bash

set -e

if [[ $(/usr/bin/id -u) -ne 0 ]]; then
    echo "Error: Must run with sudo/root"
    exit 1
fi

# check minimum supported python version
python3 -c 'import sys; minor_ver = sys.version_info.minor; sys.exit(0) if minor_ver >= 7 else ""; print(f"Incompatible Python version, must be >= 3.7.x"); sys.exit(1)' 

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

INSTALL_DIR=/usr/bin/rtcm-mqtt-streamer
INSTALLED_SERVICE_PATH=/etc/systemd/system/rtcm-mqtt-streamer.service
POPULATED_SERVICE_PATH="${SCRIPT_DIR}"/rtcm-mqtt-streamer.service
SERVICE_TPL_PATH="${SCRIPT_DIR}"/rtcm-mqtt-streamer.template.service

populate_service_template() {
    local template_path="${1}"
    local output_path="${2}"

    cp "${template_path}" "${output_path}"

    grep -o "TPL_[^ ]*" "${template_path}" | while read -r token; do
        read -p "Enter value for ${token:4}: " -u2 -r value
        sed -i.bak -e "s/${token}/${value//\//\\/}/" "${output_path}"
    done

    rm "${output_path}".bak

    echo "Created service file in ${output_path}"
}

if [ -f "${POPULATED_SERVICE_PATH}" ]; then
    echo "Populated service file already exists at ${POPULATED_SERVICE_PATH} with contents:"
    echo
    grep "ExecStart" "${POPULATED_SERVICE_PATH}"
    echo
    read -p "Overwrite? [y/n] " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        populate_service_template "${SERVICE_TPL_PATH}" "${POPULATED_SERVICE_PATH}"
    fi
else
    populate_service_template "${SERVICE_TPL_PATH}" "${POPULATED_SERVICE_PATH}"
fi

if [ -d "${INSTALL_DIR}" ]; then
    echo "Existing installation found in ${INSTALL_DIR}, overwriting..."
    rm -rf "${INSTALL_DIR}"
fi

if [ -f "${INSTALLED_SERVICE_PATH}" ]; then
    echo "Existing installed service found in ${INSTALLED_SERVICE_PATH}, overwriting..."
    rm -rf "${INSTALLED_SERVICE_PATH}"

    echo "Reloading systemd"
    sudo systemctl daemon-reload
    sudo systemctl reset-failed
fi

echo "Copying application files to ${INSTALL_DIR}"
mkdir "${INSTALL_DIR}"
cp -r certs rtcm-mqtt-streamer.py requirements.txt "${INSTALL_DIR}"

echo "Installing Python dependencies"
cd "${INSTALL_DIR}"
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
deactivate

echo "Installing rtcm-mqtt-streamer.service"
cd "${SCRIPT_DIR}"
cp rtcm-mqtt-streamer.service "${INSTALLED_SERVICE_PATH}"

echo "Reloading systemd"
sudo systemctl daemon-reload

echo "Verifying service was successfully installed"
sudo systemctl | grep rtcm-mqtt-streamer.service

echo "Finished installing rtcm-mqtt-streamer!"
echo "Enable it on boot with \`systemctl enable rtcm-mqtt-streamer\`"
echo "Start it immediately with \`systemctl start rtcm-mqtt-streamer\` "
echo
echo "Have a nice day!"