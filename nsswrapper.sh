#!/bin/sh

if test "`id -u`" -ne 0; then
    if test -s /tmp/pulse-passwd; then
        echo "Skipping nsswrapper setup - already initialized"
    else
        echo "Setting up nsswrapper mapping `id -u` to lithium"
        sed "s|^audio:\(.*\)|audio:\1,lithium|" /etc/group >/tmp/pulse-group
        if test `id -g` -ne 0; then
            echo "lithium:x:`id -g`:" >>/tmp/pulse-group
        fi
        (
            cat /etc/passwd
            echo "lithium:x:`id -u`:`id -g`:lithium:/home/lithium:/bin/sh"
        ) >/tmp/pulse-passwd
    fi

    export NSS_WRAPPER_PASSWD=/tmp/pulse-passwd
    export NSS_WRAPPER_GROUP=/tmp/pulse-group

    # Auto-detect correct libnss_wrapper path
    if [ -f /usr/lib/x86_64-linux-gnu/libnss_wrapper.so ]; then
        export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libnss_wrapper.so
    elif [ -f /usr/lib/libnss_wrapper.so ]; then
        export LD_PRELOAD=/usr/lib/libnss_wrapper.so
    else
        echo "WARNING: libnss_wrapper.so not found, skipping preload"
        unset LD_PRELOAD
    fi
fi

export HOME=/home/lithium
