# Diplomarbeit Roadmap

## Thema
Load balancing in the L4Re Operating System Framework

## Definition of Done
- [ ] Load balancer component implementation in userspace
    - [x] Dynamically distributing threads to CPUs
    - [x] Continuously monitoring system load
    - [x] Goal: maximum throughput, while:
        - [x] Keep thread restrictions
        - [x] Thread pinning onto CPUs
        - [x] Avoid sharing of CPUs between specified applications
        - [x] Never map VM vCPUs onto the same physical CPU
    - [x] Component based implementation, using:
        - [x] Capabilities
        - [x] Separate functionality and policy
        - [x] Minimality
    
- [ ] Analyze load balancing metrics
    - [x] What interfaces are needed to compute metrics
    - [x] Add needed interfaces
    - [x] Compute or I/O heavy (use up time slice or give up voluntarily)

- [ ] Asymmetric Multi-Processing awareness for
    - [x] CPU hierarchy
    - [x] P/E-Cores
        - [x] CPU micro benchmarks for scaling
    
- [ ] Performance Testing
    - [x] Efficiency & Overhead
    - [x] Keeping constraints
    - [x] Workloads:
        - [x] L4Re applications (fractal and further)

## Thesis Questions To Answer
- Find definition of "good" load balancing?
- What design achieves "good" load balancing?
- What triggers load balancing?
    - Periodically 
        - What period?
    - Overloaded CPU?
    - Idle CPU?
    - Thread creation
- How should CPU local priorities be handled in L4Re?
    - Does this concept of core local prios still makes sense?
        - Global priorities needed
- How is RT load balancing handled in this work?
    - Merged with BE into optimization goal of highest throughput
- Monitoring requires distributed system
    - Monitoring on n CPUs
    - One thread needs to make an informed decision
    - Distributed system that somehow needs to synchronize
    - Problem of local time vs. global time
    - What information can be considered up to date?

## Needed Functionality

### System Monitoring
- System
    - Average load over all CPUs 
- Per CPU
    - Load (idle time or load of threads)
        - Potentially weighted
    - Threads
    - Saturation
- Per thread
    - Priority
    - CPU usage
    - Compute or IO heavyness (time slice information)
    - Tie metrics (last/current CPU, lowest CPUID)

### Hardware Information
- CPU hierarchy
    - CPU id (x86)
- P/E Cores
    - CPU id (x86)?

### Distribution Decisions
- Periodically
    - 100ms (like Linux?)
- On Spawn
- CPU close to 100%
    - thread ready > 1
- CPU close to 0%
    - only idle thread running
- Criteria for no migration:
    - Low utilization (threshold) of all CPUs
    - High prio threads are not starving

## Existing Interfaces
- Thread

| Function | Description |
| -        | -           |
| stats_time | Get consumed time of thread in us |

- Scheduler

| Function | Description |
| -        | -           |
| info                   | max_cpu, cpus (cpus.map), sched_classes
| L4_SCHEDULER_RUN_THREAD_OP | run a thread on a scheduler and CPU with the given scheduling parameters |
| L4_SCHEDULER_IDLE_TIME_OP  | Query the idle time (in µs) of a CPU
| is_online | Query if a CPU is online

## Missing Interfaces

| Function | Description |
| -        | -           |
| L4_SCHEDULER_READY_QUEUE_OP | Get ready queue of threads for saturation

## Thread and Application Constraints
- Real-Time
    - How should this be any different from current behavior?
        - Can be done by using priority
    - For the whole application
        - Create Parameter real-time: yes
    - For arbitrarily spawned threads by an application
        - Extension scheduling interface
            - Real-Time: yes/no per run thread call
        - Extension of scheduling parameters `L4_sched_param`
            - Add real time flag

- Thread pinning
    - For the whole application
        - Create Parameter pinned: yes
    - For arbitrarily spawned threads by an application
        - Extension scheduling interface
            - Pinned: yes/no per run thread call
        - Extension of scheduling parameters `L4_sched_param`
            - Add pinning flag

- Core sharing
    - Threads are placed into groups based on cpu.map in `L4_sched_param`
    - If granularity:
        - inf: all CPUs 
        - n: on n CPUs
        - 1: on one CPU
    - Groups dont need to stay on initial CPU
    - Groups need to be migrated as a group

## Load Balancer Nr.1 - Done
- Service registry
- Setup
    - CPU map
    - Online CPUs
- Server Loop
    - Get utilization of all CPUs
        - Problem of idle time
    - On new thread:
        - Move to lowest utilization CPU

- Label ATOMIC, FIXME: make load read/writes atomic
- FIXME: for loops over cpus is not checking online
    - probably needs to be checked every time when maps is not continous

## Load Balancer Nr.2 - Done
- Balancing during runtime
    - Thread queue per CPU
        - Remove invalid thread caps
        - Solved by `thread_stats_time` 
            - sys call returns invalid, when thread does not exist anymore
    - On overloaded cpu move thread
        - Ready queue is growing

- Thread information (Requires Kernel API extension of `thread_stats_time`)
    - Estimates thread state (Ready, Blocked)
        - If compte time > 0 is Ready, blocked otherwise
    - Read priority 
        - Should by done by proxy, not by call, need to handle prios anyway
    - Compute or IO heavy
    - `thread_stats_time` (extend to thread_stats for more info)
        - volunarily yielding the CPU for compute/IO heaviness

- Thread Capabilities
    - used to compare thread objects in own run_queue implementation
        - Compare_cap used in find
    - need to move cap slot
        - `server.realloc_rcv_cap(0);` for new cap slot
        - Use L4Re::Util::Unique_cap for handling multiple capabilities
    - caps can be compared but it is pointer and rights (`cap_equal`)
        - same pointer with different rights is not equal
        - comparison is complicated but sched_proxy is called by pthread.h
        - rights are equal at that point anyway

- Priority Awareness
    - Priority Scaling
        - cut off in default priority band
        - scale according to given loba factory priority band

- LoadBalancerFactory
    - `create_op` checking ned script cmd line parameters
    - used from ahci driver
    - scanning for priorities default otherwise
    - registering scheduler_proxy 

## Load Balancer Nr.3 - Done
- Thread Groups
    - Built from initial sp.affinity `cpu_scheduling_set`
    - Separation between mutual exclusive masks
    - Rebalancing built around groups

    - Implementation Details:
        - Use std::list instead of vector as pointers are invalidated on insert of new items

- Separating code into single files
    - File per class
    - Separating policy and functionality
    - Keep data structures and classes self contained

- Read Thread Ready state
    - Extend user space/kernel sys call
    - New structs/unions needed because of Mword utcb structure

- Thread Pinning
    - New Thread Groups struct for pinned groups (at max CPU many)
    - No `update_cpu_mask` for them as masks should stay original
    - New optional run_thread parameter
        - Alternative: extended sched_param
            - High ripple effects as pthread lib must be adapted
            - Can be done in the future
    - If pinned is called:
        - Only one CPU in mask is allowed
        - Otherwise EINVAL 
    - Implementation:
        - Extend Scheduler proxy/svr interface
        - Operation run_thread_pinned with pinn parameter
        - Defaulting/overloading is hard in interfaces
        - New call is easier solution with less ripple effects

- CPU Hierarchy (from core-minion example)
    - cpuid asm available on x86 in user land (security issue?)
    - Discover different leafs (modes)
    - Read leaf and subleaf information 
    - Problem if Kernel built with MAX_CPU 64 and above
        - 32 bit cpu mask is too small (iterating twice)
        - Use Cpu_flat bitset to get full bitmap
    - Testing AMP is difficult
        - QEMU does not support 0x1A leafs of different kinds
        - Will always read uniform processors
        - P/E Cores need to be set manually, therefore cant be tested with `cpuid()`

## Load Balancer Nr.4 - Done
- Enhanced Thread Information tracking
    - Use Array with 0/1 to keep track of last n times the thread ran
    - 0 thread left voluntarily
    - 1 thread was preempted
    - Optimize Array to Mword with bit shift and | operator
    - Keeps track of 32/64 last times thread was rescheduled
        - Little overhead and memory size

- Fixing poller thread
    - Wasnt initialized with loba prio

- Fixing run thread
    - Did not cover many corner cases
        - Reassigning any sched_params to Tracked_thread on run_thread
        - Reevaluate pinned -> group class switching
        - Find target cpu before creating Tracked_thread
        - Tracked_thread constructor for elimination of undefined behavior

- Avoid usage of Doubles/Floats entirely
    - Avoids usage of FPU and its loading/restoring overhead
    - Precision of percentages can be achieved by using Int * 1000 or * 1000000
    - Used for:
        - Load calculations (CPU/Thread)
        - Priority scaling

- Usage of caps_equal_no_rights
    - Caps to same kernel object with different rights are !=
        - This breaks bookkeeping
    - Change caps_equal (no_rights) to only regard obj and not rights
    - Underlying problem:
        - Bookkeeping breaks, threads on CPUs they are not supposed to be
        - Monitoring sys_thread_stats -> not as IPC but as DRQ
        - DRQs imply potential priority inversion
            - Executed on behalf of DRQ Context with its prio
            - Must be avoided at all cost!
    - Change to caps_equal_no_rights solves problem only partially
    - Underlying problem:
        - Migration is asynchronous and thread dependend
        - If thread is in transit and sys_thread_stats is called
        - DRQ is done by kernel for you -> cant be checked or avoided
            - not even with timeout 0 
        - Because bookkeeping is out of sync with threads actual state
        - Solution: write new sys_thread_stats that returns error on DRQ 

- sys_thread_extended_stats
    - Extended version returning time, ready and heavyness
    - If thread is not on current CPU, not DRQ but return -ENOENT
    - No info about thread better than potential blocking
    - Monitor checks error code and moves on
    - Solves thread mirgration in transit problem (above)

- Optional printing
    - Done at compile time therefor no overhead 
    - Making debug info optinal with constexpr DEBUG flag
    - Making benchmark info optional with constexpr BENCHMARK flag

## Load Balancer Nr.5
- CPU power detection
    - Micro calculation loop measured by `rdtsc()`
    - `mops = iterations / (time / 1000)`
    - Find minimum mops and derive relative speeds compared to slowest CPU
        - Round power to nearest tenth
    - TODO could be improved with more advanced test to have a better assumption of "faster" CPU

- OOP for all bookkeeping data structures
    - Were mostly public structs/classes
    - Shift logic into classes themselves
    - Make all attributes private

- Thread safe bookkeeping access
    - Load-balancer is multithreaded
        - Poller thread and scheduling proxy access run_queues, groups, threads concurrently
    - Use Locking for Run_queue, Thread_group, Thread_groups, Tracked_thread and Cpu_state, Benchmarking
    - TODO: improve by using atomics in the right place
        - DONE: for Benchmarking, Tracked_thread (where possible), Cpu_state

- Refactored Benchmarking
    - Using Atomics instead of Locks
    - Store Counters and Timers in enums to make use of arrays
    - This scales better than having individual variables + getter/setter
    - Extend Timers to all functions of polling and rebalancing
    - Fine granular timing to find slow sections in hot path

- Fix proxy prio
    - Wasnt initialized to LOBA_PRIO
    - Scheduler->run_thread blocks for indeterministic amount of time

- Move Poller and Proxy thread to !=CPU0
    - Moe blocks CPU0 with prio 255 if called (from any CPU and any prio)
    - This blocks poller thread and scheduling proxy
    - Moving proxy to CPU1 (if there is only 1 CPU makes no sense anyway)
    - Moving poller to prefered CPU2 if available (CPU1 otherwise)

- Atomics for Tracked_thread and Cpu_state
    - Cpu_state easy only primitive data types
    - Tracked_thread mostly easy
        - `l4_sched_param_` is not accessible via atomcis
        - Data structure too big needs to be guarded by lock
        - Could not be split up and reconstructed because `l4_sched_cpu_set` is also still too big
        - Found bug in placement move(thread, cpu_nr)
            - need to adjust prio to loba prio because going to original scheduler->run_thread() directly

- Decouple CPU monitoring and Poller thread (now Commander thread)
    - Monitor threads update Cpu_state every MONITOR_CYCLE_US using absolute timeouts
        - Commander does the same with BALANCE_DELAY_US in delay
        - Commander checks which CPUs are outdated
        - TODO: still need to decide what to do with that outdated CPU info for dynamic_groups.update_cpu_masks()
        - Rebalances(only with synced CPUs)

    - Check for synced when using `pick_cpu()` because run_thread of proxy could get outdated values of Cpu_states and send Threads to CPUs that are occupied by high prio threads
        - Check what CPUs are in sync at the beginning of run_thread
        - Synced CPUs are always needed for new threads or for existing ones because `pick_cpu` is called in both cases
    
    - Locking Problem
        - Cpu_state.update() and rebalance access the same run_queues
        - If CPU Monitor gets stuck because of high prio Task this blocks rebalancing because of run_queue Mutex
        - Is partly solved by disregarding out of sync CPUs 
            - As there is no iterating for vload or thread balancing on this specific blocked CPU/run_queue anymore
            - If printf hits after sync check the problem remains
    - Locking Solution
        - Write the timestamp of the Cpu_state as last operation of Monitoring loop
        - This way the CPU releases any locks before the time is updated
        - This way the Commander cant be blocked by the mutex of run_queues anymore

    - Printf Problem
        - If sync works for CPU0 and then printf hits CPU0 is blocked
        - rebalancing scheduler->run_thread then blocks on CPU0 as well
        - Would need to check if CPU0 is blocked or not right before migration
        - Very hard (if not impossible) to do because of timing and cross core reasons

## Benchmarking
- Hardware
    - CPU Intel i9-13900K 3.0 GHz (32 Threads)
    - RAM DDR5 3600 GHz (128 GB)

- To compare systems using CPU benchmarks
- Benchmarks need to test behavior of the load balancer
- Characteristics to test agains:
    - Compute Load (Compute Heavy)
    - Usage of P/E Cores (CPU Hierarchy)
    - Memory Heavy (I/O Heavy)
    - Scalablility (64 instances on 2 CPUs vs 64 instances on 8 CPUs)
- Comparability vs. POSIX Linux

- Possible benchmarks SPEC CPU 2006/2017/2026
    - 2006 manageable in resources, can spawn multiple threads for balancing
    - 2017 & 2026 min. 2 GB RAM per thread of a benchmark
        - Resource intense although state of the art not useful for testing load-balancer
    - 2006 1 GB RAM per thread
        - Outdated applications but useful for testing load-balancer

- SPEC CPU 2006 
    - 403.gcc
        - Compiler, Integer
    - 429.mcf
        - Combinatorial Optimization, Integer
    - 462.libquantum
        - Physics: Quantum Computing, Integer
    - 470.lbm
        - Fluid Dynamics, Floating Point

- Problem with SPEC CPU 06
    - Benchmarks are aquiring GB memory in 4KiB pages
    - When freed moe has to unmap all this memory one by one
    - Takes insufferable amount of time
    - All benchmarks are also printing results which requires cons/moe to be available 

- Problem with SPEC CPU 17
    - Ported mcf and lbm to L4Re but take up to 10min
    - Not feasible for 100 runs

- Possible benchmarks analogous to SPEC CPU types
    - [CoreMark](https://github.com/eembc/coremark) (Integer compute, control flow, function calls) [gcc]
    - [STREAM](https://www.cs.virginia.edu/stream/FTP/Code) (Memory bandwidth, pointer chasing) [mcf]
    - [Whetstone](https://www.netlib.org/benchmark/whetstone.c) (Floating Point, Fixed Point, Math operations) [lbm]
    - [tinymembench](https://github.com/ssvb/tinymembench) (memory bandwidth and latency) [libquantum]

    - Need to be ported to L4Re
        - [x] CoreMark (~30s) ITERATIONS = 1'000'000
        - [ ] STREAM (~30s) ARRAY_SIZE = 1'000'000, NTIMES = 15'000
        - [x] Whetstone increased (~30s) LOOP = 100'000 II = 100
        - [ ] tinymembench reduced (~30s) MAXREPEATS = 4, wait time 0.5->0.2
            - Retained C copy backwards
            - Retained C copy
            - Retained C 2-pass copy
            - Retained C fill
            - Removed C copy backwards (32 byte blocks)
            - Removed C copy backwards (64 byte blocks)
            - Removed C copy prefetched (32 bytes step)
            - Removed C copy prefetched (64 bytes step)
            - Removed C 2-pass copy prefetched (32 bytes step)
            - Removed C 2-pass copy prefetched (64 bytes step)
            - Removed C fill (shuffle within 16 byte blocks)
            - Removed C fill (shuffle within 32 byte blocks)
            - Removed C fill (shuffle within 64 byte blocks)
    - Linux ports all compiled with -O2
        - Tried to keep behavior close to L4Re port
        - [x] CoreMark (~20s) ITERATIONS = 1'000'000
        - [ ] STREAM (~17s) ARRAY_SIZE = 1'000'000, NTIMES = 15'000
        - [x] Whetstone increased (~26s) LOOP = 100'000 II = 100
        - [ ] tinymembench reduced (~21s) MAXREPEATS = 4, wait time 0.5->0.2
            - Retained C copy backwards
            - Retained C copy
            - Retained C 2-pass copy
            - Retained C fill
            - Removed C copy backwards (32 byte blocks)
            - Removed C copy backwards (64 byte blocks)
            - Removed C copy prefetched (32 bytes step)
            - Removed C copy prefetched (64 bytes step)
            - Removed C 2-pass copy prefetched (32 bytes step)
            - Removed C 2-pass copy prefetched (64 bytes step)
            - Removed C fill (shuffle within 16 byte blocks)
            - Removed C fill (shuffle within 32 byte blocks)
            - Removed C fill (shuffle within 64 byte blocks)
    - All printf statements in valid comput paths removed

- Compiler Optimization flags:
    - O2
    - mtune=generic
    - m64
    - fno-strict-aliasing
    - fno-omit-frame-pointer
    - fstack-protector
    - fwrapv-pointer
    - fPIE

### Benchmarking Test Cases

- Baseline (100 runs each)
    - [x] Linux
    - [x] Native L4Re
    - [x] Static
    - [x] AMP 100ms
- Parallel (200 runs total 100 each)
    - [x] Medium 
        - [x] Linux
        - [x] Static
        - [x] AMP 10/20/50/100ms
    - [x] Full
        - [x] Linux
        - [x] Static
        - [x] AMP 10/20/50/100ms
    - [x] Over
        - [x] Linux
        - [x] Static
        - [x] AMP 10/20/50/100ms
- CPU AMP CoreMark Scalability
    - [x] 2 CPUs
        - [x] Linux
        - [x] Static
        - [x] AMP 10/20/50/100ms
    - [x] 4 CPUs
        - [x] Linux
        - [x] Static
        - [x] AMP 10/20/50/100ms
    - [x] 8 CPUs
        - [x] Linux
        - [x] Static
        - [x] AMP 10/20/50/100ms

- Overhead Measurements
    - 0 Threads
        - [x] AMP 10/20/50/100ms
    - 10 Threads
        - [x] AMP 10/20/50/100ms
    - 100 Threads
        - [x] AMP 10/20/50/100ms
    - 500 Threads
        - [x] AMP 10/20/50/100ms
    - 1000 Threads
        - [x] AMP 10/20/50/100ms
    - 2000 Threads
        - [x] AMP 10/20/50/100ms

## Balancing Algorithms

### Initial Placement (static placement)
- Decision at run_thread time
- Put thread on lowest load cpu
    - according to Group Cpu mask

### Group Rebalancing
- Iterate Groups and place groupwise
- Inside Groups choose lowest load cpu
    - according to mask overlap constraints

### Load Aware Balancing (based on actual thread load)
- Hard Constraints:
    - Thread Grouping (placement mask)
    - CPU load (only over to underloaded cpu migrations)
- Soft Constraints:
    - Migration cost
    - Load transferred (projected load)
    - Fitness on destination cpu

- Prio Fitness for Destination
    - return remaining capacity for migration thread prio at destination
    - return SUM(thread_load of thread.prio < migration_thread_prio)

- Algorithm
    - Calc mean_cpu_load
    - Identify overloaded cpus
    - for src : overloaded cpus
        - identify underloaded cpus
        - for thread : src.run_queue
            - for dst : underloaded cpus
                - check if allowed in thread group mask
                - test if dst would be overloaded by migration
                - score(thread, dst) // store max score and dst
        - migrations.add(thread, dst)
        - dst add projected load of migration thread (scaled load)
    - execute all migrations

- When handling us times and `LOAD_SCALING = 1'000'000` datatype `unsigned` is easily overflown
    - use `uint64_t or l4_uint64_t` instead because `long` must not be 64 bits on every architecture

- Does not handle fairness
    - CPU0, thread prio 5 compute heavy, load 100%
    - CPU1, 4 threads prio 5 compute heavy load 100%
    - will not move because load is (even scaled load) is equal

- Introduce second run if categorization by load could not find overloaded cpu
    - probably because all CPUs have the same load (most likely 100%)
    - Sort by ready_queues
    - Move from longer ones to short ones

### Load Aware Balancing (based on preemption demand)

- Threads:

| Name | Description | Calculation |
| - | - | - |
| weight | weight of thread | proportional with priority |
| cpu_usage | % consumed cpu time | thread_stats_time |
| ready_factor | Prefer ready threads over blocked | Ready ? 1 : 0.5 |
| preemptions | Compute or I/O heavy | thread_stats_time |
| demand | Decaying preemptions | SUM(premption_n * DECAY^n)/MAX_DECAY, n <= 20 |
| migration_cost | Cost of migration | 1 - cpu_usage |
| vload | Virtual load | demand * weight * ready_factor |
| score(t, dst) | Score threads with destination cpus | (1 - dst_load) * capacity_at_dst(prio) * vload * migration_cost|

- Preemptions are measure for compute demand of a thread
- Scaled with number of threads and does not decay if thread is suspended/preempted
- Cpu_usage is limited to 100% CPU time, preemption demand is not
- If more threads are preempted more threads need to compute
- If all of them are preempted by higher prio, preemption demand still remains (virtual load)
- vload can be scaled by weight and readyness as before
- vload is unaffected by hidden load on CPU0 as preemption demand stays the same even if moe, ned, sigma0 are "stealing cpu time" as cpu usage is not taken into account anymore
- vload metric only fails of high prio thread is spawned to cpu with even higher prio thread and other CPUs are loaded with loads of low prio threads that have the same total vload as the two high and higher prio threads (starving the lower high prio thread)
- Being blocked in ready_factor is accounted for double because last (most valuable) bit in preemption demand will be 0
- Allows CPUs with more active threads to reflect that in vload metric (compared to previous version)
- Thread CPU usage is indicator for cache content as thread that computed last is likely to have warm cache, therefore higher migration cost

- Resolves problem of second migration iteration by ready_queue length
- Because vload can scale with the number of threads if all need to compute

[Linux_thread_weight](https://lwn.net/Articles/531853/)

- CPUs:

| Name | Description | Calculation |
| - | - | - |
| cpu_power | Power relative to weakest CPU | n times as fast as slowest (scaled in 10ths) (only for P/E), 1 otherwise |
| load | Cpu usage | 1 - idle_time |
| vload | Virtual load | SUM(vload of threads in run_queue) * load * cpu_power |
| mean_cpu_load | Average load over all cpus | SUM(vload) / num_cpus |
| overloaded | Overloaded CPUs (migrate from) | vload > mean_load * (1 + epsilon) && load > 90%|
| underloaded | Underloaded CPUs (migrate to) | vload < mean_load * (1 - epsilon) |

- CPU vload can be computed as beforehand with normal load (SUM threads)
- Multiply with actual cpu usage to:
    - benefit CPU0 if hidden load is experienced
    - make CPU viable even if high prio thread is calculating little
- Scale vload of threads also by CPU power as CPU with more instruction per cycle has higher throughput and therefore less load as E-Core

- Maybe observe over/under loaded twice to avoid spikes because 100ms window is long

## Optimizations

### Hardware/Compiler Optimizations
- Excessive use of const/constexpr functions (PARTLY)
    - Allows compiler to make compiletime optimizations

- Avoid usage of Doubles/Floats entirely (DONE)
    - Avoids usage of FPU and its loading/restoring overhead
    - Precision of percentages can be achieved by using Int * 1'000'000

- Have Cache aligned Data Structues
    - CPU runtime monitoring structues are distributed in multiple caches
    - If alinged threre is no bouncing and efficient parallel access/writing
    - Otherwise bouncing and poor cache performance 

### Software Optimizations
- Efficient Monitoring threads Nr.1 (DONE)
    - Self timeout, to update without IPC from outside
    - Sleep (Timeout) is IPC call to itself (but no outside partner)
    - Problem with that is asynchronous timing for poller rebalancing
    - Solved by using absolute time timeouts
    - Much lower overhead than cross core IPI every period

- Efficient Monitoring threads Nr.2
    - Thread probing needs to be done synchronously because of dynamic structues
    - Polling of monitors could be done via interrupts to save time
        - Currently n times synchronous IPC call
        - Preferred n times parallel IPI to monitor and wake poller when all n answers have returned
        - Reduces overhead from O(N) to O(max(probing calls)) 
        - The probing call scales with the number of threads on that CPUs

- Batched stats_time_extended system call
    - Monitor threads are probing all threads of a run_queue one by one
    - It would be more efficient to batch the sys call thread_stats_time
    - Reduces stats_time sys calls from O(n) to O(ceil(n/batch_size))
    - Hard to implement because of executing entities and current RPC framework
    - RPC requires consistent Cap transfer, unsuitable for reading n (max 21 - 63 Mwords / 3 (64 t_time + 8 ready + 64 preemptions)) thread states at once
    - Could reduce 64 preemptions to 32 for 64 + 8 + 32 for 31 threads per batch
    - Executing entity unclear, implement in Thread or Context, Scheduler is unclean (dummy Caps)

- Userland Balancing Problem
    - Datastructures can be preempted at any point in time on any CPU for arbitrary amount
    - If Commander thread tries to balance and operates on those structs it is blocked
    - Could use non-blocking primitives
    - At least RW-lock, maybe lockfree 
    - PARTIALLY SOLVED by synced CPU check of commander

- Avoid Heap Allocation
    - During runtime can cause page faults and high allocation times 
    - Either try to use global states
        - Bad for cache performance
        - Can be initialized once at load-balancer start
    - Use stack allocatable datastructures
        - Need to be sized during compile time
        - Bad for memory efficiency
        - Dont require heap memory at all 

## Getting Started
- Diplom Thesis of Philipp
- L4Re Load Balancer (LoBa) in gerrit
- L4Re Core Minion in gerrit

## Hurdles
- Problem Timing: idle time accumulates faster than wall clock time
    - roughly 2 times as fast
```
load-bal| monitoring [0: idle 175370975, last 175270064, now 736000, last 627000]
load-bal| monitoring [0: idle 100911.000000, time 109000.000000, res 0.925789]
load-bal| monitoring [1: idle 176904553, last 176657754, now 738000, last 629000]
load-bal| monitoring [1: idle 246799.000000, time 109000.000000, res 2.264211]
load-bal| monitoring [2: idle 176938587, last 176692087, now 740000, last 631000]
load-bal| monitoring [2: idle 246500.000000, time 109000.000000, res 2.261468]
load-bal| monitoring [3: idle 176969744, last 176723939, now 742000, last 633000]
load-bal| monitoring [3: idle 245805.000000, time 109000.000000, res 2.255092]
```
- Solution Timing: on x86
    - enable: "Fine grained CPU time" in kernel for precise idle time
    - enable: "SYNC_CLOCK" in kernel for precise wall clock time
            - requires  "HAS_SYNC_CLOCK" to be enabled

- Problem Capabilities: different Caps different rights, same rights move the same kernel object
- Capabilities are compared with rights, if they are different this is considered not equal even if they point to the same object
- This breaks bookkeeping structures as the Cap rights are not needed for the load balancer in order to call run_thread on the main scheduler
    - 432000 == 431000 KO = x81 valid
    - 432000 =! 431000 KO = x85 valid
    - 433000 =! 432000 KO = x85 not valid
```
load-bal| proxy: receiving run thread 0x432000 for cpu 1 prio 2
load-bal| proxy: run moving thread stored=0x431000 (aka param=0x432000) from cpu2 to cpu0
load-bal| proxy: run thread stored=0x431000 (aka param=0x432000) on cpu0 (load=97) prio 2->5
run_thread thread 0x81 to cpu 0 with prio 5 on current cpu 0

load-bal| proxy: receiving run thread 0x432000 for cpu 1 prio 2
load-bal| New thread added to group
load-bal| proxy: run thread stored=0x432000 (aka param=0x432000) on cpu0 (load=97) prio 2->5
run_thread thread 0x85 to cpu 0 with prio 5 on current cpu 0

load-cli| [worker  0] started  load=cpu      aff=core0
load-bal| proxy: receiving run thread 0x433000 for cpu 1 prio 2
load-bal| New group CPU assignment: 0...0001
load-bal| New thread added to new group
load-bal| proxy: run thread stored=0x433000 (aka param=0x433000) on cpu0 (load=99) prio 2->5
run_thread thread 0x85 to cpu 0 with prio 5 on current cpu 0
```

- Kernel stats_time uses DRQ on your behalf to get thread information that is on different CPU
    - Threads that are in transit are on no CPU and responsible for their own migration (with their own priority) potential priority inversion with the Load-Balancer when updating thread time with stats_time() because it is sys call 

- When handling us times and `LOAD_SCALING = 1'000'000` datatype `unsigned` is easily overflown
    - use `uint64_t or l4_uint64_t` instead because `long` must not be 64 bits on every architecture

- When being told that the test hardware has 16 CPUs
    - Identifying a bug in your hierarchy functionality
    - Also identifying that the machine has 24 cores not only 16

- Scheduler->run_thread blocks for indeterministic amount of time
    - Because Load-Balancer main thread was only one not raised to LOBA_PRIO

- Polling thread blocks for indeterministic amount of time right at beginning
    - Because when someone prints to Moe this is spinnlocking the kernel
    - If a low prio thread prints continously this blocks moe systemwide
    - Moving poller thread and proxy thread to CPU1-2 and CPU1 helps significantly
    - Poller thread is still always waiting for all monitors to return including mon-CPU0 that can continously block on moe 
```
load-bal| 	 polling:      avg=62704 max=172020 us
load-bal| 	 ping_monitors avg=0 max=0 us
load-bal| 	 update_thread avg=0 max=2 us
load-bal| 	 update_idle   avg=2 max=7 us
load-bal| 
load-bal| 	 update_groups avg=4 max=18 us
load-bal| 
load-bal| 	 rebalance     avg=7 max=12 us
load-bal| 	 update_vload  avg=0 max=1 us
load-bal| 	 calc_mean     avg=1 max=2 us
load-bal| 	 calc_migr     avg=1 max=10 us
```

```
load-bal| 	 polling:      avg=2816 max=36758 us
load-bal| 	 ping_monitors avg=0 max=0 us
load-bal| 	 update_thread avg=0 max=1 us
load-bal| 	 update_idle   avg=1 max=12 us
load-bal| 
load-bal| 	 update_groups avg=3 max=27 us
load-bal| 
load-bal| 	 rebalance     avg=737 max=36574 us
load-bal| 	 update_vload  avg=183 max=36548 us
load-bal| 	 calc_mean     avg=732 max=36550 us
load-bal| 	 calc_migr     avg=1 max=6 us
```

```
load-bal| 	 polling:         avg=2691 max=33342 us
load-bal| 	 ping_monitors    avg=0 max=0 us
load-bal| 	 update_thread    avg=0 max=18 us
load-bal| 	 update_idle      avg=1 max=20 us
load-bal| 
load-bal| 	 update_groups    avg=1 max=9 us
load-bal| 
load-bal| 	 rebalance        avg=281 max=11141 us
load-bal| 	 calc_mean        avg=1 max=2 us
load-bal| 	 update_cpu_vload avg=0 max=1 us
load-bal| 	 update_run_vload avg=0 max=1 us
load-bal| 	 calc_migr        avg=278 max=11135 us
```

- Locking Problem
    - Cpu_state.update() and rebalance access the same run_queues
    - If CPU Monitor gets stuck because of high prio Task this blocks rebalancing because of run_queue Mutex
    
- printf() problem
    - If printf is called then Moe blocks CPU0
    - If something is migrated to or from CPU0 this requires the scheduler to execute a DRQ onto CPU0
    - During printf interrupts are closed and DRQ blocks
    - Therefore scheduler can block for indeterministic amount of time

- Rebalance experiences weird delays of up to 20ms
    - This is not during:
        - CPU list sorting
        - Calculating migrations
        - Migrations themselves
        - Therefore only memory allocation remains
    - Changing structs to Stack based instead of heap std::vector
    - Problem remain and Moe was doing severe number of Unmap calls 
