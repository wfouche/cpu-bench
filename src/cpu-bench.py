#---------------------------------------------------------------------------------------
#
# Program to benchmark CPUs and determine a server's degree of parallelism (DOP).
#
# Author: W. Fouché
#
# Intel:
#   Disable Intel SpeedStep
#   Disable Intel TurboBoost
#   Enable Intel HyperThreading
#
# Power:
#   Enable SMT
#
#---------------------------------------------------------------------------------------

from __future__ import print_function, division

# import datetime; print(datetime.datetime.now())

BUILD_VERSION   = "1.2.2"
BUILD_TIMESTAMP = "2021-02-19 21:30:44.047214"

#---------------------------------------------------------------------------------------

spr_scale_factor = 1.0

#---------------------------------------------------------------------------------------

import datetime
import os
import sys
import socket
import subprocess
import time
import gc
import getopt
import platform
import timeit
import multiprocessing

#---------------------------------------------------------------------------------------

import defaults

use_c_extension = defaults.use_c_extension

HOSTNAME = socket.gethostname()

#---------------------------------------------------------------------------------------

if platform.system() == "Windows":
    exe_compute_N = "./compute_N.exe"
else:
    exe_compute_N = "./compute_N.%s"%(platform.machine())

#---------------------------------------------------------------------------------------
	
csv_report_header = True

#---------------------------------------------------------------------------------------

#
# http://pythoncentral.io/measure-time-in-python-time-time-vs-time-clock/
#
	
default_timer = timeit.default_timer

#---------------------------------------------------------------------------------------

def to_seconds(s):
    t = s.split(":")

    a = t[:1]
    b = t[1:]

    n = int(a[0])

    for e in b:
        n = n*60+int(e)

    return n

#---------------------------------------------------------------------------------------

def format_n1k(n):
    """
    Utility function to display an integer value
    with commas as thousand separators.
    Example: 1234567 is displayed as 1,234,567
    """
    s = "%d"%(n)
    t = []
    while len(s) > 3:
        x = s[-3:]
        t.append(x)
        s = s[:-3]
    t.append(s)
    s = ""
    for e in t:
        if len(s) == 0:
            s = e
        else:
            s = e + "," + s
    return s

#---------------------------------------------------------------------------------------

def compute_N_native(N):
    line = subprocess.check_output([exe_compute_N, "%d"%(N)], universal_newlines=True)
    duration_this_CPU = float(line)
    return duration_this_CPU

#---------------------------------------------------------------------------------------

def compute_N_python(N):
    """
    Compute the time it takes to increment an integer 
    variable 'n' by 1, 'N' times; starting at zero.
    """

    #i = long(0)
    i = 0 + 2**64  # long() function not in Python 3.x
    
    #n = long(N)
    n = int(N) + 2**64  # long() function not in Python 3.x

    x0 = default_timer()

    # -- portable and slow (but HT friendly)
    while i < n:
        i += 1   

    #for e in xrange(N):
    #    pass
     
    # -- crashes on 32bit and 64bit Windows which both use 4 byte longs.
    # --
    # -- OverflowError: Python int too large to convert to C long
    # --
   
    # Re-implementd main xrange loop as two nested xrange loops
    # in order to resolve the C long overflow problem on Windows.
    
    #for e in xrange(N//1000):
    #    for f in xrange(1000):
    #        pass
        
    x1 = default_timer()

    return x1-x0

#---------------------------------------------------------------------------------------

if use_c_extension:
    compute_N = compute_N_native
else:
    compute_N = compute_N_python

#---------------------------------------------------------------------------------------

def calc_seed_value():
    duration = 0
    seed_value = 1000
    seed_value = 1
    count = 0
    while (duration < 1.0) and (count < 100):
        seed_value = seed_value*2
        #seed_value = (seed_value//1000)*1000
        duration = compute_N(seed_value)
        count += 1
    if count == 100:
        print("\nError: calc_seed_value - unable to calibrate CPU benchmarking loop.")
        sys.exit(1)
    return seed_value

#---------------------------------------------------------------------------------------

def benchmark_one_CPU(seed_value, csv_report):
    target_duration = 30.0
    if not csv_report: print("")
    if not csv_report: print("Performance of 1 LCPU:")
    if not csv_report: print("")
    N_next = seed_value

    for i in range(4):
       N = N_next
       duration_one_CPU = compute_N(N)
       spr = N / duration_one_CPU
       spr = spr / 1000000.0 * spr_scale_factor
       if not csv_report:
           print("    LCPU 0: It took %.3f seconds to reach %s at SPR(%.1f)"%(duration_one_CPU, format_n1k(N),spr))
       N_next = int((target_duration * N) / (duration_one_CPU))
       #N_next = (N_next//1000)*1000

    dop = 1.0
    
    # Compute SPR.
    spr = int(dop * N / duration_one_CPU)
    spr = spr / 1000000000.0 * spr_scale_factor

    #if not csv_report: print("")   
    #if not csv_report: print("    SPR: %.1f"%(spr))
    #if not csv_report: print("    DOP: %.f"%(dop))
    
    delta = abs(target_duration - duration_one_CPU)
    if delta > 1.0:
        print("")
        print("System Error - system unstable with 1 LCPU - seed value could not be determined.")
        sys.exit(1)
       
    return (N, duration_one_CPU, dop, spr)

#---------------------------------------------------------------------------------------

def waitfor_time_ss(ss):
    # Wait till we reach ??:??:ss
    while time.localtime().tm_sec != ss:
        # sleep for 100 milliseconds
        time.sleep(100.0 / 1000.0)

#---------------------------------------------------------------------------------------

def waitfor_time_hh_mm(hh, mm):
    t = time.localtime()
    #print("Current time: %d:%d:%d"%(t.tm_hour, t.tm_min, t.tm_sec))
    # Wait till we reach hh:mm:00
    #print("Waiting till: %d:%d:00"%(hh,mm))
    t = time.localtime()
    while not ((t.tm_hour == hh) and (t.tm_min == mm)):
        # sleep for 100 milliseconds
        time.sleep(100.0 / 1000.0)
        t = time.localtime()
    #print("Done!!")        

#---------------------------------------------------------------------------------------

def benchmark_all_CPUs(script_name, num_CPUs, N, duration_one_CPU, csv_report, dop_one_CPU, spr_one_CPU, multi_threaded=False):
    if not csv_report:
        print("")

    if not csv_report:
        if multi_threaded:
            print("Performance of %d LCPUs (using a thread per LCPU):"%(num_CPUs))
        else:
            print("Performance of %d LCPUs (using a process per LCPU):"%(num_CPUs))
    if not csv_report: print("")

    current_tm_sec = time.localtime().tm_sec
    if not (current_tm_sec in range(0,10)):
        print("")
        print("System Error - took too long to call benchmark_all_CPUs!")
        sys.exit(1)
    
    timestamp = datetime.datetime.now().isoformat()
    duration_all_CPUs = 0.0
    L = []
    if multi_threaded:
        # Using multiple threads, one per logical CPU.
        if use_c_extension:
            p = subprocess.Popen([exe_compute_N, "%d"%(N), "%d"%(num_CPUs)], stdout=subprocess.PIPE)
        else:       
            printf("cpu-bench.py: multi-threading support is only enabled when the C_extension is activated.\n")
            system.exit(1)
    else:
        # Using multiple processes, one per logical CPU.
        for i in range(num_CPUs):
            if use_c_extension:
                p = subprocess.Popen([exe_compute_N, "%d"%(N), "0"], stdout=subprocess.PIPE)
            else:
                p = subprocess.Popen([sys.executable, script_name, "--mi=%d"%(N)], stdout=subprocess.PIPE)
            L.append(p)
            
    current_tm_sec = time.localtime().tm_sec
    if not (current_tm_sec in range(0,20)):
        print("")
        print("System Error - took too long to start all background processes!")
        sys.exit(1)

    lcpu_id = 0
    SPR = 0.0
    rlist = []
    if multi_threaded:
        out, err = p.communicate()
        list = out.splitlines()
        for i in range(len(list)):
            duration_this_CPU = list[i].decode()
            duration_this_CPU = float(duration_this_CPU)
            spr = N / duration_this_CPU
            spr = spr / 1000000.0 * spr_scale_factor
            if not csv_report:
                rlist.append("    LCPU-%d: It took %.3f seconds to reach %s at SPR(%.1f)"%(lcpu_id,duration_this_CPU,format_n1k(N),spr))
            duration_all_CPUs += duration_this_CPU
            lcpu_id += 1
            SPR += spr
    else:
        for p in L:
            out, err = p.communicate()
            list = out.splitlines()
            duration_this_CPU = list[0].decode()
            duration_this_CPU = float(duration_this_CPU)
            spr = N / duration_this_CPU
            spr = spr / 1000000.0 * spr_scale_factor
            if not csv_report:
                rlist.append("    LCPU %d: It took %.3f seconds to reach %s at SPR(%.1f)"%(lcpu_id,duration_this_CPU,format_n1k(N),spr))
            duration_all_CPUs += duration_this_CPU
            lcpu_id += 1
            SPR += spr
        
    if not csv_report:
        for line in rlist:
            print(line)

    if not csv_report: print("")
    
    dop = num_CPUs * (duration_one_CPU / (duration_all_CPUs / num_CPUs))

    # Compute SPR.
    spr = SPR

    if not csv_report:
        print("Benchmark Score:")
        print("")
        print("    NUM_LCPUs : %d"%(num_CPUs))
        print("    DOP       : %.3f"%(dop))
        print("    SPR       : %.1f"%(spr))
        print("")
        print("    Timestamp : %s"%(("%s"%datetime.datetime.now()).split('.')[0]))

    if csv_report:
        global csv_report_header
        if csv_report_header:
            csv_report_header = False
            print("HOSTNAME,DATETIME,NUM_LCPUs,DOP,SPR")
        print("%s,%s,%d,%.3f,%.1f"%(HOSTNAME, timestamp[:19], num_CPUs, dop, spr))
        
    return (dop, spr)

#---------------------------------------------------------------------------------------

def child_process(N):
    """
    Invoked by a child process when benchmarking the performance
    of a multiple CPUs. Each process executes compute_N(N).
    """
    
    # All processes wait to start at exactly the same time.
    # Wait till we reach hh:mm:00        
    waitfor_time_ss(30)        
    
    # Compute N and display the elapsed time to the console (pipe).
    print(compute_N(N))

#---------------------------------------------------------------------------------------

def get_params(opt_list, trace=0):
    list = []
    for e in opt_list:
        if e[0] == "":
            pass
        else:
            if e[1] == None:
                list.append(e[0])
            else:
                list.append(e[0]+"=")   

    opts, args = getopt.getopt(sys.argv[1:], '', list)
    d = {}
    for o, a in opts:
        d[o] = a

    if trace: print("")   
    keys = d.keys()
    for k in keys:
        if trace: print("[%s]"%(k), "[%s]"%(d[k]))
    if trace: print("")

    return d    

#---------------------------------------------------------------------------------------
  
opt_list = \
[
    ("auto",            None),
    ("use_threads",     None),
    ("spr_scale_factor","=="),
    ("num_cpus",        "=="),
    ("mi",              "=="),
    ("si",              "=="),
    ("sc",              "=="),
    ("csv_report",      None),
    ("waitfor_time",    "=="),
]

#---------------------------------------------------------------------------------------

def main_process(num_cpus, csv_report, N, duration_one_CPU, dop_one_CPU, spr_one_CPU, use_threads): 
    # Now get all CPUs to count to 'N' and measure the elapsed time for individual CPUs.
    # Use this information to compute a CPU scaling index as well as a performance
    # rating for the server.
    
    return benchmark_all_CPUs(sys.argv[0], num_cpus, N, duration_one_CPU, csv_report, dop_one_CPU, spr_one_CPU, use_threads)

if __name__ == "__main__":
    d = get_params(opt_list)

    if ("--use_threads" in d.keys()):
        use_threads = True
    else:
        use_threads = False

    if ("--spr_scale_factor" in d.keys()):
        spr_scale_factor = float(d["--spr_scale_factor"])

    if ("--num_cpus" in d.keys()) or ("--auto" in d.keys()):
    
        if ("--num_cpus" in d.keys()):
            num_cpus = int(d["--num_cpus"])

        if ("--auto" in d.keys()):
            num_cpus = multiprocessing.cpu_count()
        
        csv_report = ("--csv_report" in d.keys())

        if not csv_report:
            print("")
            print("CPU-bench:")
            print("")
            print("    %s (%s)"%(BUILD_VERSION, BUILD_TIMESTAMP))
            print("")
            print("    C_extension: %s"%("enabled" if use_c_extension else "disabled"))
            print("")
            print("Hostname:")
            print("")
            print("    %s"%(HOSTNAME))
            print("")
            print("Operating System Environment:")
            print("")            
            print("    %s"%(platform.platform()))
            print("")
            print("Python Version:")
            print("")
            print("    %s"%(sys.version.replace("\n"," ")))
            print("")
            print("Runtime Arguments:")
            print("")            
            print("    %s: %s"%(sys.executable,sys.argv))
            print("")
            print("Server Hardware:")
            print("")            
            print("    Number of LCPUs (logical CPUs, hardware threads): %d (%s)"%(num_cpus,platform.machine()))

        if ("--si" in d.keys()) and ("--sc" in d.keys()):
            si = to_seconds(d["--si"])
            sc = int(d["--sc"])
        else:
            sc = 0
            si = 0
        
        seed_value = calc_seed_value()

        gc.disable()
        # Compute how far a single CPU can count in roughly 30 seconds.
        # Example return value: (541270585, 30.532)  
        (N, duration_one_CPU, dop_one_CPU, spr_one_CPU) = benchmark_one_CPU(seed_value, csv_report)
        gc.enable()
        
        if ("--waitfor_time" in d.keys()):
            v = d["--waitfor_time"]
            e = v.split(":")
            hh = int(e[0])
            mm = int(e[1])
            waitfor_time_hh_mm(hh,mm)
        else:
            waitfor_time_ss(0)
        
        if sc == 0:
            (dop, spr) = main_process(num_cpus, csv_report, N, duration_one_CPU, dop_one_CPU, spr_one_CPU, use_threads)        
        else:
            dop_list = []
            spr_list = []
            time_start = time.time()
            time_delta_secs = si
            for i in range(sc):
                (dop, spr) = main_process(num_cpus, csv_report, N, duration_one_CPU, dop_one_CPU, spr_one_CPU, use_threads)
                dop_list.append(dop)
                spr_list.append(spr)
                if i < sc-1:
                    time_now = time.time()
                    while time_now < time_start+time_delta_secs:
                        time_now = time.time()
                        # sleep for 100 milliseconds.
                        time.sleep(100.0/1000.0)
                    time_start += time_delta_secs
            
            d_min = min(dop_list)
            d_max = max(dop_list)
            d_avg = (1.0*sum(dop_list))/len(dop_list)
            d_rng = d_max - d_min

            s_min = min(spr_list)
            s_max = max(spr_list)
            s_avg = (1.0*sum(spr_list))/len(spr_list)
            s_rng = s_max - s_min
                
            if csv_report:
                timestamp = datetime.datetime.now().isoformat()
                print("")
                #print("%s,%d,%.f,%.f"%(timestamp[:19], num_cpus, d_min, s_min))
                #print("%s,%d,%.f,%.f"%(timestamp[:19], num_cpus, d_max, s_max))
                print("%s,%d,%.1f,%.1f"%(timestamp[:19], num_cpus, d_avg, s_avg))               

        if not csv_report:                
            print("")

    elif ("--mi" in d.keys()):
        gc.disable()
        # Child processes
        child_process(int(d["--mi"]))
    else:
        print("Options --auto or --num_cpus should be specified for platform %s."%(platform.system()))
        sys.exit(0)

    sys.exit(0)

#-----------------------------------
