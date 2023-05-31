#
# meters.py
#
# Author: Griffith Thomas
# Copyright 2022 Spyderbat, Inc. All rights reserved.
#

"""
A series of functions to handle the processing and formatting of top data for
the header meters.
"""


from math import nan
from typing import Dict, Optional
from datetime import timedelta

from spydertop.model import AppModel
from spydertop.utils import add_palette, header_bytes, sum_element_wise

# --- Disk IO Meter ---


def sum_disks(disks: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    """Sums the values of disk reads and writes for all disks, ignoring the
    duplicates or invalid disks"""
    # see https://github.com/htop-dev/htop/blob/main/linux/Platform.c#L578-L593 for reference
    prev_disk_name = ""
    filtered_disks = {}

    for disk_name, values in disks.items():
        # ignore these disks
        if disk_name.startswith("dm-") or disk_name.startswith("zram"):
            continue

        # assuming sda comes before sda1, skip all duplicate partitions
        if prev_disk_name != "" and disk_name.startswith(prev_disk_name):
            continue

        prev_disk_name = disk_name
        filtered_disks[disk_name] = values

    return sum_element_wise(filtered_disks.values())  # type: ignore


def get_disk_values(model: AppModel, muid: str):
    """Generates the string for the disk IO meter"""
    # modeled after https://github.com/htop-dev/htop/blob/main/DiskIOMeter.c#L34-L108
    disk = model.get_value("disk", muid)
    prev_disk = model.get_value("disk", muid, previous=True)
    if disk is None or prev_disk is None:
        return None
    disk_count = len(disk.keys()) + 0.00000001
    disk = sum_disks(disk)
    prev_disk = sum_disks(prev_disk)
    time_elapsed_ms = model.get_time_elapsed(muid) * 1000
    percent_used = round(
        (disk["io_time_ms"] - prev_disk["io_time_ms"])
        / time_elapsed_ms
        / disk_count
        * 100,
        1,
    )
    read_bytes = (disk["sectors_read"] - prev_disk["sectors_read"]) * 512
    write_bytes = (disk["sectors_written"] - prev_disk["sectors_written"]) * 512
    return {
        "percent_used": percent_used,
        "read_bytes": read_bytes,
        "write_bytes": write_bytes,
    }


def show_disk_io(model: AppModel):
    """Generates the string for the network meter"""
    values: Optional[Dict[str, int]] = None
    if model.selected_machine is not None:
        values = get_disk_values(model, model.selected_machine)
    else:
        net_values = [get_disk_values(model, muid) for muid in model.machines.keys()]
        filtered = [n for n in net_values if n is not None]
        if len(filtered) > 0:
            values = sum_element_wise(filtered)  # type: ignore
        else:
            values = None

    if values is None:
        return add_palette("  ${{{meter_label}}}Disk I/O: ${{1,1}}No Data", model)

    return add_palette(
        "  ${{{meter_label}}}Disk IO: ${{{meter_label},1}}{percent_used}% ${{{meter_label}}}\
read: ${{2}}{read_bytes} ${{{meter_label}}}write ${{4}}{write_bytes}",
        model,
        percent_used=values["percent_used"],
        read_bytes=header_bytes(values["read_bytes"]),
        write_bytes=header_bytes(values["write_bytes"]),
    )


# --- Network Meter ---


def get_network_values(model: AppModel, muid: str):
    """Gets the network values for a given machine"""
    network_totals = model.get_value("network", muid)
    prev_net_totals = model.get_value("network", muid, previous=True)
    if network_totals is None or prev_net_totals is None:
        return None
    network_totals = network_totals["total"]
    prev_net_totals = prev_net_totals["total"]
    time_elapsed_sec = model.get_time_elapsed(muid)
    rx_bytes = (
        network_totals["bytes_rx"] - prev_net_totals["bytes_rx"]
    ) / time_elapsed_sec

    tx_bytes = (
        network_totals["bytes_tx"] - prev_net_totals["bytes_tx"]
    ) / time_elapsed_sec

    reads = network_totals["reads"] - prev_net_totals["reads"]
    writes = network_totals["writes"] - prev_net_totals["writes"]

    return {
        "rx_bytes": rx_bytes,
        "tx_bytes": tx_bytes,
        "reads": reads,
        "writes": writes,
    }


def show_network(model: AppModel):
    """Generates the string for the network meter"""
    values: Optional[Dict[str, int]] = None
    if model.selected_machine is not None:
        values = get_network_values(model, model.selected_machine)
    else:
        net_values = [get_network_values(model, muid) for muid in model.machines.keys()]
        filtered = [n for n in net_values if n is not None]
        if len(filtered) > 0:
            values = sum_element_wise(filtered)  # type: ignore
        else:
            values = None

    if values is None:
        return add_palette("  ${{{meter_label}}}Network: ${{1,1}}No Data", model)
    rx_bytes = header_bytes(values["rx_bytes"])
    tx_bytes = header_bytes(values["tx_bytes"])
    if not (tx_bytes[-1]).isdigit():
        tx_bytes += "i"
    if not (rx_bytes[-1]).isdigit():
        rx_bytes += "i"
    return add_palette(
        "  ${{{meter_label}}}Network: rx: ${{2}}{rx}b/s ${{{meter_label}}}\
write: ${{4}}{tx}b/s ${{{meter_label}}}({reads}/{writes} reads/writes)",
        model,
        rx=rx_bytes,
        tx=tx_bytes,
        reads=values["reads"],
        writes=values["writes"],
    )


# --- Task Meter ---


def show_tasks(model: AppModel):
    """Generates the string for the task meter"""
    tasks = model.get_value("tasks", muid=None)
    if tasks is None:
        return add_palette("  ${{{meter_label}}}Tasks: ${{1,1}}No Data", model)
    # this is necessary because of how tasks seem to be counted
    processes = 0
    muids = (
        [model.selected_machine] if model.selected_machine else model.machines.keys()
    )
    for muid in muids:
        processes += len(model.get_value("processes", muid) or [])
    if processes == 0:
        task_count = "${1,1}Not Available"
    else:
        task_count = processes - tasks["kernel_threads"]
    running = tasks.get("running", 0)
    kthreads = tasks.get("kernel_threads", 0)
    threads = tasks.get("total_threads", 0) - kthreads

    thread_style = "${8,1}" if model.config["hide_threads"] else "${2,1}"
    thread_lbl_style = (
        "${{8}}" if model.config["hide_threads"] else "${{{meter_label}}}"
    )
    kthread_style = "${8,1}" if model.config["hide_kthreads"] else "${2,1}"
    kthread_lbl_style = (
        "${{8}}" if model.config["hide_kthreads"] else "${{{meter_label}}}"
    )
    return add_palette(
        "  ${{{meter_label}}}Tasks: ${{{meter_label},1}}{task_count}"
        + thread_lbl_style
        + ", {thread_style}{threads} "
        + thread_lbl_style
        + "thr"
        + kthread_lbl_style
        + ", {kthread_style}{kthreads} "
        + kthread_lbl_style
        + "kthr${{{meter_label}}}; ${{2,1}}{running} ${{{meter_label}}}running",
        model,
        task_count=task_count,
        threads=threads,
        kthreads=kthreads,
        running=running,
        thread_style=thread_style,
        kthread_style=kthread_style,
    )


# --- Load Average Meter ---


def show_ld_avg(model: AppModel):
    """Generates the string for the load average meter"""
    ld_avg = model.get_value("load_avg", muid=None)
    num_machines = len(model.machines) if model.selected_machine is None else 1

    if ld_avg is None or len(ld_avg) == 0:
        return add_palette("  ${{{meter_label}}}Load average: ${{1,1}}No Data", model)

    for i, load in enumerate(ld_avg):
        ld_avg[i] = f"{float(load) / num_machines:.2f}"

    if len(ld_avg) == 1:
        return add_palette(
            "  ${{{meter_label}}}Load average: ${{{background},1}}{ld_avg[0]}, ${{1,1}}No Data",
            model,
        )
    if len(ld_avg) == 2:
        return add_palette(
            "  ${{{meter_label}}}Load average: ${{{background},1}}{ld_avg[0]},"
            " ${{{meter_label},1}}{ld_avg[1]}, ${{1,1}}No Data",
            model,
        )
    return add_palette(
        "  ${{{meter_label}}}Load average: ${{{background},1}}{ld_avg[0]} \
${{{meter_label},1}}{ld_avg[1]} ${{{meter_label}}}{ld_avg[2]}",
        model,
        ld_avg=ld_avg,
    )


# --- CPU Meter ---


def update_cpu(i, model: AppModel, muid: str):
    """Determines the values for use in the CPU meter"""
    # reference: https://github.com/htop-dev/htop/blob/main/linux/Platform.c#L312-L346
    cpu = model.get_value("cpu_time", muid)
    prev_cpu = model.get_value("cpu_time", muid, previous=True)
    if (
        cpu is None
        or prev_cpu is None
        or f"cpu{i}" not in cpu
        or f"cpu{i}" not in prev_cpu
    ):
        return [0, 0, 0, 0]
    cpu = cpu[f"cpu{i}"]
    prev_cpu = prev_cpu[f"cpu{i}"]

    time_elapsed_sec = model.get_time_elapsed(muid)
    clk_tck = model.get_value("clk_tck", muid) or nan
    values = [0, 0, 0, 0]
    values[0] = (cpu["nice_time"] - prev_cpu["nice_time"]) / clk_tck / time_elapsed_sec
    values[1] = (
        (cpu["user_space_time"] - prev_cpu["user_space_time"])
        / clk_tck
        / time_elapsed_sec
    )
    values[2] = (
        (cpu["system_time"] - prev_cpu["system_time"]) / clk_tck / time_elapsed_sec
    )
    values[3] = (
        (
            cpu["guest_time"]
            + cpu["steal_time"]
            - prev_cpu["guest_time"]
            - prev_cpu["steal_time"]
        )
        / clk_tck
        / time_elapsed_sec
    )
    return values


# --- Memory Meter ---


def update_memory(model: AppModel):
    """Determines the values for use in the memory meter"""
    # reference: https://github.com/htop-dev/htop/blob/main/linux/LinuxProcessList.c#L1778-L1795
    # and https://github.com/htop-dev/htop/blob/main/linux/Platform.c#L354-L357
    mem = model.memory
    if not mem:
        return (None, None)
    total = mem["MemTotal"]
    buffers = mem["Buffers"]
    used_diff = mem["MemFree"] + mem["Cached"] + mem["SReclaimable"] + buffers
    used = total - used_diff if total >= used_diff else total - mem["MemFree"]
    shared = mem["Shmem"]
    cached = mem["Cached"] + mem["SReclaimable"] - shared
    values = [0, 0, 0, 0]
    values[0] = used
    values[1] = buffers
    values[2] = shared
    values[3] = cached

    return (total, values)


# --- Swap Meter ---


def update_swap(model: AppModel):
    """Determines the values for use in the swap meter"""
    # reference: https://github.com/htop-dev/htop/blob/main/linux/LinuxProcessList.c#L1793-L1795
    mem = model.memory
    if not mem:
        return (None, None)
    total = mem["SwapTotal"]
    cached = mem["SwapCached"]
    used = total - mem["SwapFree"] - cached
    values = [0, 0]
    values[0] = used
    values[1] = cached

    return (total, values)


# --- Uptime ---


def show_uptime(model: AppModel):
    """Generates the string for the uptime meter"""
    uptime = ", ".join(
        str(timedelta(seconds=model.timestamp - mach["boot_time"]))
        for mach in model.machines.values()
    )
    if len(uptime) == 0:
        return add_palette("  ${{{meter_label}}}Uptime: ${{1,1}}No Data", model)
    return add_palette(
        "  ${{{meter_label}}}Uptime: ${{{background},1}}{uptime}",
        model,
        uptime=uptime,
    )
