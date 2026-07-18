#!/bin/sh
action=$1
logger -p notice -t blue-merle-toggle  "Called... ${action}"


. /lib/functions/gl_util.sh


# Ignore empty or unexpected values so switch bounce or malformed hook
# invocations cannot wipe /tmp/sim_change_switch mid-operation.
case "$action" in
    on|off) : ;;
    "")
        logger -p notice -t blue-merle-toggle "Empty action, ignoring"
        exit 0
        ;;
    *)
        logger -p notice -t blue-merle-toggle "Unexpected action '$action', ignoring"
        exit 0
        ;;
esac

# Mark this invocation as "driven by the physical toggle" so that stage1's
# CHECK_ABORT does not immediately kill the process on the first modem
# retry (the switch file is legitimately "off" until we write "on" below).
mkdir -p /tmp/blue-merle
: > /tmp/blue-merle/toggle-driven

if [ "$action" = "on" ]; then
    mcu_send_message "Blue Merle ${action}"
    echo "on" > /tmp/sim_change_switch
    logger -p notice -t blue-merle-toggle "Running Stage 1"
    # The timeout must exceed the stage's own worst-case budget
    # (CFUN retries + EGMR + readbacks + MCU sleeps ≈ 100 s), or a
    # SIGTERM can land between the EGMR write and the runtime-store
    # update / safe poweroff, leaving a half-finished swap.
    flock -n /tmp/blue-merle-switch.lock timeout 150 /usr/bin/blue-merle-switch-stage1 \
        || logger -p notice -t blue-merle-toggle "Stage 1 lock busy or failed"

elif [ "$action" = "off" ]; then
    # Only run stage2 if stage1 finished its part.
    if [ -f /tmp/blue-merle-stage1 ]; then
        flock -n /tmp/blue-merle-switch.lock timeout 150 /usr/bin/blue-merle-switch-stage2 \
            || logger -p notice -t blue-merle-toggle "Stage 2 lock busy or failed"
    else
        logger -p notice -t blue-merle-toggle "No Stage 1; Toggling Off"
    fi
    echo "off" > /tmp/sim_change_switch
fi

# Clean up the toggle marker; a fresh run will recreate it.
rm -f /tmp/blue-merle/toggle-driven

logger -p notice -t blue-merle-toggle "Finished Switch $action"
sleep 1
