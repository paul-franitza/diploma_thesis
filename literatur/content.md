# Abstract

# Introduction

## Outline

# Technical Beckground

## Terminology

## Related Work

## Operating Systems

### Monolithic Kernels

### Microkernel-Based Operating Systems

### L4Re Operating System Framework

## Microkernel Philosophy

### Kernel vs. Userland
Interruptible and Preemptable

### Components
Proxy Pattern

### Information Exchange

#### Inter Process Communication

#### Shared Memory

#### Cross-Core Communication
DRQs and IPIs

### Capabilities
Objects and Rights manangement

## CPU Scheduling

### Real-Time vs. Best Effort

### Priorities

#### Priority Inversion

## Load Balancing
Definition, Goals, Trigger

### Approaches

#### Push
#### Pull
#### Centralized

## Asymmetric Multi-Processing 

### Heterogeneous CPU Architecture
P/E Cores

# Design

## Architecture Overview
- All Done on x86_64
- The Scheduling Proxy
    - Proxy Pattern
    - Intercepting Scheduler calls like run_thread from application
- Monitoring
    - One thread per CPU to track CPU idle thread time and threads running on that CPU
- The Commander
    - Aggregates Monitor data and triggers rebalancing
- Thread Groups
    - Define CPU set that a thread is allowed to run on
- CPU Hierarchy
    - CPU discovery
    - Hierarchy structure and identifying power of CPUs in P/E Core case 

## Scheduling Proxy for Load Balancing
- Scheduling Interface
    - Existing Interface
    - Additional Interface Extenstions
- Shadows Run Queues / System State (Threads)
- Thread register in run_thread (never deregister)
- Following Factory Pattern
    - Can create multiple instances and layer them

## Monitoring System State
- One thread for all (would need to migrate), centralized inefficient
- Monitoring thread per CPU
- Idle time & run queue threads (idle time only on current CPU)
- Want to find out what threads are ready or blocked
    - No scheduler system call that returns this information (would need to add new sys call to kernel)
    - Monitor threads by calling stats_time sys call (cpu time)
    - Extend this call and also return ready/blocked state

## Commander Thread
- Collect information from monitor threads
- Synchronize with monitor threads
	- Using IPC (synchronized)
	- Notifications via Interrupts (async, IPI costly)
	- Absolute Timeouts (async, no IPI)
        - Requires global time with a synchronized clock all participants have access to
        - need to find outdated CPUs
- Update virtual CPU load for synced CPUs
    - Cant migrate to or from blocked CPUs
    - Need to be marked as unsynced
- Rebalances -> Centralized Approach

## Thread Groups
- Assures Threads stay on assigned CPUs (relative to other assignments)
    - UVMM, virtual CPUs and their interrupt threads -> same CPU is required
- Allows for reordering CPUs in the CPU sets while ensuring disjunct CPU sets remain disjunct

## Priority Translation
- Proxy allows for reassigning priorities
- Can enforce policy
- Cutoff (Default)
- Scaling, sclaes from old into new priority band
- L4Re perceives priorities as core local
    - Concept breaks when migrating threads
    - Global priorities need to be assumed

## CPU Hierarchy Scanning
- Took inspiration from exisitng kernel module (core-minion)
    - Different approach to exploring the hierarchy after information was read
- cpuid on x86 allows reading hierarchy information in userland
- No such premitive on arm

### CPU Power Detection
- If P/E system tiny benchmark to measure instructions / second
- Scale CPU power -> used to scale CPU load according to power level

# Implementation

## Scheduling Proxy
- L4Re Apps see cap slots not caps themselves
    - realloc_rcv_cap avoids overide of old slot
    - Taking ownership over cap
- Threads can call run_thread multiple times
    - ITAS second time to raise priority
    - compare caps with sys call: cap_equal (O(n) many)
    - Cap is obj. + rights if rights change is not the same cap
    - Requires kernel change: cap_equal_no_rights compares not regarding access rights

## Monitoring
- Threads register at proxy, never deregister, avoid tombstones
    - Thread probing done anyway, needs to flag dead threads
    - stats_time returns error on non existing thread cap
- Deletion of dead threads complicated because of multiple structures containing thread reference
    - No sinlge source of truth
    - Deletion needs to be organized
- stats_time sys call starts DRQ if thread is on different CPU
    - E.g. in transit during migration
    - DRQ is on behalf execution (requested thread) -> potential priority inversion
    - Return error code instead
    - Outdated info better than blocking for arbirtary amount of time

### Timing
- On x86 requires "Fine graind CPU time" in kernel
- Done by enabling "SYNC_CLOCK" -> requires "HAS_SYNC_CLOCK" to be enabled
- Otherwise no us granularity timing, only ms granularity and deviating clocks in system

## Load Balancing
- Requires definition of load/overload for CPUs
- Intuitively can choose CPU usage (inverse idle time)
    - Concept breaks when all CPUs hit 100% usage (0% idle time)
    - 5 * 20 % usage = 1 * 100% usage
    - Usual case because priority based scheduling
- Problem is only 1 dimensional
    - USE Methode by Brandon Gregg
    - Utilization, Saturation, Errors
- Load needs to reflect compute demand of threads on CPU (CPU only has limited capacity to satisfy demand)
    - virtual load or vload
    - Cant use Linux concept of virtual runtime because not running on budgets/quantums
    - Preemptions are useful indicator
        - If timeslice used up or thread preempted write 1 (compute, demand high)
        - else (IPC, yield, sleep) write 0 (I/O, demand low)
        - Store in machine word as sliding window -> shift left 1 and OR with current value
        - Use sliding window for demand calculation (Linux aging, 32ms for half-life)
        - Does not age if thread is ready but suspended because only new entries are added if thread stops running
    - Compute vload from demand, priority (weight), and ready/blocked
- Sum vload over threads of CPU, identify overloaded ones and move threads to underloaded CPUs
    - Actual CPU usage can now be used as indicator if caches are warm (cost of migration)

### Thread Groups
- Use std::bitsets for fast access and calculation
- Otherwise iterating all disjunctive CPU sets and computing the resulting available CPU set can be tideous and slow

## Threadsafe Datastructures
- State like structures for CPU and Thread via atomics (as far as possible)
    - only locks for attributes that are too big in size
- Mutex locking for bookkeeping strucutres like run queues and thread groups

## Distributed System in Userland
- Can be preempted at any time (Proxy, Commander, Monitors)
- Proxy/Commander preemption -> cant help it
    - while holding lock blocks others
- If Monitor blocked while holing lock
    - Proxy/Commander should not block themselves, would halt system
    - Need to detect blocked Monitor via outdated timestamp
    - Monitor updated timestamp only if run queue lock is released
    - Can still create blocking szenarios but they are less likely
- Commander updates virtual load of CPU state
    - Could be done by Monitors but if blocked and marked outdated by Commander the Monitor could overwrite virtual load during Commander rebalances
    - Outdated mark stays until the Commander calculates virtual load again next monitoring cycle
    - During mark the Proxy will regard this CPU with minimum priorty when choosing destination CPU for new threads

## Thread Information (not needed)
- stats_time -> only cpu usage
- stats_time_exteded -> cpu usage, preemptions/yields, ready/blocked
    - Also return ENOENT error code when thread currently not CPU to avoid DRQ

## L4Re Migrations
- Migration is issued at kernel scheduler
- Migration itself is done by thread with own thread priority (fine, since stats_time is robust)
- If destination CPU is blocked by higher prio thread
    - Kernel scheduler sys call blocks until unblocked and call can finish
    - Synchronized CPUs help avoid this but no guarantee because CPUs can block at any given point in time

## CPU0 Problem (Moe)
- Moe single instance handling prints (very slow ms per char)
- Moe singel instance memory returns of dataspaces, calls Unmap (ms per call)
- Always running with highest priority on CPU0 and therefore blocking everything else
- Not the whole system state observable

## Optimizations
- DONE
    - Avoid usage of floating point calculations
        - Omits usage of FPU (load, store, flush)
    - Efficient monitoring
        - Not using IPIs and still making use of parallel execution
- TRIED
    - Batched stats_time_extended sys call
        - Could transfer 21/31 thread states at once
        - Not possible via scheduler (no executing entity)
            - RPC Framework does not allow for variable number of caps
            - Filling up with dummy caps seems unclean
        - Could be implemented as Context/Thread class function
        - Was no bottle neck so no further investigation
    - Avoid Heap Allocation in hot path
        - repeated allocation of std lib structs during rebalancing
        - switch to compile time known sizes yielded no measurable speedup but more complicated code
        - Statically assumed size introduces internal memory offcuts in stack

## Summary
- Architecture diagramm showing all changes
- Reuse achitectural graphics from gesign but show syscalls that changed or where used
- Show SYNC_CLOCK
- cpuid on x86


# Evaluation

## Hardware
- 32 Threads, 24 Cores (8 P, 16 E), 128 GB DDR5 RAM 3600 GHz
- Intel i9-139000K 2.20/3.00 GHz , 4.30/5.80 GHz Turbo

## Benchmarks

### SPEC CPU 2006 Ports
- 1 GB of RAM needed per instance
- malloc uses 4KB pages -> Moe unmaps iteratively
- up to 250.000 unmap calls ~1ms per call
- Benchmarks print results -> would also block on Moe, avoided by using Cons and hiding all output

### SPEC CPU 2017 Ports
- 2 GB of RAM needed per instance
- Runtime exceeded 10min, not feasable for frequent testing

### Small Ports
- CoreMark -> CPU heavy
- Whetstone -> CPU heavy

- STREAM -> Memory heavy
- Tinymembench -> Memory heavy
    - Although reduced in memory size (<10MB) while porting still suffering from same problem as SPEC CPU benchmarks

- All printing removed
- Parameter Adjustments

## Test Cases
- 100 Instances one after another
    - Native L4Re
    - Load Balancer Static
    - Load Balancer AMP 100ms Intervals
    - Linux EEVDF

- N CoreMark Instances on N CPUs (2,4,8)
    - Load Balancer Static
    - Load Balancer AMP 10/20/50/100ms Intervals
    - Linux EEVDF

- Low, Full, Over loaded Scenarios CoreMark and Whetstone (8,16,64 instances each) till 100 reached
    - Load Balancer Static
    - Load Balancer AMP 10/20/50/100ms Intervals
    - Linux EEVDF

- Monitoring Overhead
    - 0, 10, 100, 500, 1000, 2000 idle threads
    - Could go higher but pthread library running into issues, potentially becuase of cap table size (even with raised size limit)
    - Load Balancer AMP 10/20/50/100ms Intervals

## Results

- Static Distribution (Proxy) Suffering
    - Would need to recalculate vload if thread added
    - vload during add is 0 therefore will pile on one CPU
    - Until monitoring collects data
    - Also cant add and hope that monitors will update in between because thread probing works only CPU local
    - Thread only migrated at the end of scheduler proxy run_thread() 


## Discussion

### Improve Benchmarking
- Target Instances divisible by all batch sizes -> 128 would have been a better choice

# Future Work

## Extended Design
- Provide Real-Time Constraints
    - Highest prio will not always run even when there is a CPU that would allow for that
    - Breaks RT assumptions
    - If enabling migrations in RT system need further investigation on time boundness of migrations themselves and WCET influence
- NUMA, cache, memory, CPU power awareness
    - Currently only CPU aware
    - Not aware of NUMA, cache, memory hierarchies
    - Power level sqeezes multi-dimension computational parallelism into one factor
    - Improve Benchmarks for fine granular CPU power detection
        - Maybe vector approach on different accellerator units (SIMD, FPU, SVE, SME)
    - Behavior Awareness
        - Identify thread characteristics to make deliberate P/E choices
        - Performance level breaks AMP structure down to SMP level

## Security Issue
- Thread groups allow for increasingly fast growing number of groups if there are enough CPUs
    - Mallicous application could spawn threads of one group each to let load balancer run out of memory
    - crashing it for all other applications that also received this load balancer as scheduler 
    - Somewhat contained by limited way to construct cpu_sets in l4re 

## Optimizations
- Batched stats_time_extended sys call
- Efficient solution for cap_equal(_no_rights) iterational lookup
    - Maybe there is none because of how caps are mananged in L4Re
- Usage of stack allocatable structures in hot path to avoid page faults at runtime
- Efficient cache usage with aligned data structures
    - Should prevent cache line bounding of different CPU states

# Conclusion / Summary






