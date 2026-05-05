package swiftdeploy.infrastructure

import future.keywords.if
import future.keywords.contains

default allow := false

allow if {
    disk_ok
    cpu_ok
    mem_ok
}

disk_ok if {
    input.disk_free_gb >= data.thresholds.min_disk_free_gb
}

cpu_ok if {
    input.cpu_load_1m <= data.thresholds.max_cpu_load
}

mem_ok if {
    input.mem_free_percent >= data.thresholds.min_mem_free_percent
}

reasons contains msg if {
    not disk_ok
    msg := sprintf(
        "disk_free_gb is %.1f, minimum required is %.1f",
        [input.disk_free_gb, data.thresholds.min_disk_free_gb]
    )
}

reasons contains msg if {
    not cpu_ok
    msg := sprintf(
        "cpu_load_1m is %.2f, maximum allowed is %.2f",
        [input.cpu_load_1m, data.thresholds.max_cpu_load]
    )
}

reasons contains msg if {
    not mem_ok
    msg := sprintf(
        "mem_free_percent is %.1f%%, minimum required is %.1f%%",
        [input.mem_free_percent, data.thresholds.min_mem_free_percent]
    )
}

decision := {
    "allow":   allow,
    "reasons": reasons,
    "domain":  "infrastructure",
    "checked": {
        "disk_free_gb":     input.disk_free_gb,
        "cpu_load_1m":      input.cpu_load_1m,
        "mem_free_percent": input.mem_free_percent,
    },
}