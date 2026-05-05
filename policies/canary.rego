package swiftdeploy.canary

import future.keywords.if
import future.keywords.contains

default allow := false

allow if {
    error_rate_ok
    latency_ok
}

error_rate_ok if {
    input.error_rate_percent <= data.thresholds.max_error_rate_percent
}

latency_ok if {
    input.p99_latency_ms <= data.thresholds.max_p99_latency_ms
}

reasons contains msg if {
    not error_rate_ok
    msg := sprintf(
        "error_rate is %.2f%%, maximum allowed is %.2f%%",
        [input.error_rate_percent, data.thresholds.max_error_rate_percent]
    )
}

reasons contains msg if {
    not latency_ok
    msg := sprintf(
        "p99_latency is %.0fms, maximum allowed is %.0fms",
        [input.p99_latency_ms, data.thresholds.max_p99_latency_ms]
    )
}

decision := {
    "allow":   allow,
    "reasons": reasons,
    "domain":  "canary",
    "checked": {
        "error_rate_percent": input.error_rate_percent,
        "p99_latency_ms":     input.p99_latency_ms,
        "window_seconds":     input.window_seconds,
    },
}