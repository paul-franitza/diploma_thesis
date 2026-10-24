# Related Work

## General Purpose Operating System Scheduling

### Linux

The Completely Fair Scheduler (CFS) of Linux balances load hierarchically across cores using a sophisticated load metric rather than simple thread counts.
The approach measures CPU load as $\frac{\text{thread}_{\text{weight}} \times \text{thread}_{\text{CPU utilization}}}{\text{cgroup size}}$, accounting for thread priority, actual CPU usage, and fairness between applications.

Load balancing occurs in three scenarios: periodically, when cores become idle, and when threads are created or woken up.
CPUs are organized hierarchically by resource sharing, from SMT pairs and cache domains to NUMA nodes grouped by interconnect distance.

One designated core per scheduling domain performs the balancing by comparing average loads across scheduling groups and migrating up to 32 threads at a time from the busiest cores.
To avoid excessive migrations that hurt NUMA locality, CFS only balances between distant NUMA nodes when imbalance exceeds 25\%, with higher thresholds for nodes further apart.
Additionally, cache-locality heuristics favor placing woken threads near their waker or previous core to improve cache reuse~\cite{wasted_cores, cfs_vs_ule}.

### Windows

Windows employs a pull-based migration strategy where idle processors actively steal work rather than loaded processors pushing threads away.
When a processor becomes idle, the idle scheduler (KiSearchForNewThread) scans other processors' ready queues, prioritizing the shared ready queue (for threads with no affinity restrictions) before examining local queues, proceeding from the current NUMA node to progressively distant nodes while respecting affinity constraints.
At thread creation, the ideal processor is assigned in round-robin fashion using a per-process seed that increments with each new thread, distributing threads evenly across available processors from the outset.
Subsequently, thread placement prioritizes cache locality through a hierarchical fallback strategy:
(1) ideal processor, (2) last processor (maximizing cache hit probability), (3) current processor (performing the scheduling decision), (4) same SMT set as ideal processor (sharing core cache), and (5) lowest-numbered available processor.
NUMA-awareness keeps threads on their ideal node to minimize remote memory access latency, while SMT-awareness prefers idle physical cores over hyper-threading pairs to avoid execution resource contention.
Additionally, quantum-end migration proactively relocates threads when their SMT set becomes busy while other SMT sets in the ideal node remain fully idle, preventing performance degradation from competing threads sharing core resources.
This approach balances load opportunistically while minimizing cache invalidation and NUMA penalties, with migrations occurring only when processor selection algorithms determine superior placement based on current system state rather than through periodic rebalancing~\cite{windows_internals, clr_inside_out}.

## AMP Aware Balancing

### AMPS

AMPS (Li, Baumberger, Koufaty, Hahn — Intel, SC'07) extends Linux 2.6.16 with three mechanisms for performance-asymmetric multicore/NUMA systems: (1) asymmetry-aware load balancing, which scales a core's load by its computing power so balance means proportional rather than equal thread counts; (2) faster-core-first scheduling, which keeps fast cores populated (up to 3 threads before spilling to slow cores) whenever they're under-utilized, since balance alone doesn't guarantee fast-core usage; and (3) NUMA-aware migration, which uses per-thread/per-node resident-set tracking to predict whether a migration's cache-miss cost will be worth it, gating running-thread migrations accordingly. Evaluated on real hardware (clock-modulated to emulate asymmetry), it gets median speedups of 1.16 (SMP) and 1.07 (NUMA), plus better fairness and run-to-run repeatability, with negligible software migration overhead.

- Core mechanism relevant to your "AMP Aware Scheduling" section: AMPS modifies only find_busiest_group()/find_idlest_group() and the load metric itself — i.e., it's a minimal, drop-in change to Linux's existing distributed load-balancing infrastructure, not a new balancer. Good contrast point if loba takes a more architectural/from-scratch approach.
- Scaled load definition (L = run_queue_length / P, balanced when Lmax − Lmin ≤ 1) is the direct precursor to most later AMP-aware balancing metrics — worth stating explicitly since your own load metric (preemption pressure) is a different design point.
- Faster-core-first is a placement heuristic, not a balancing algorithm — it explicitly avoids per-thread fairness bookkeeping ("would require global ordering of all threads") in favor of the simpler policy of always filling fast cores first. Useful to cite when motivating why more sophisticated metrics (like yours) might be needed.
- NUMA-migration overhead prediction (RSS-based) is essentially a heuristic proxy for cache locality — relevant if your thesis discusses migration cost as a factor in balancing decisions on AMP hardware, though this is NUMA- rather than core-type-specific.

### HASS

HASS (Heterogeneity-Aware Signature-Supported scheduler) matches threads to heterogeneous cores using offline-generated architectural signatures (reuse-distance-based cache-miss profiles) instead of online performance monitoring. At scheduling time it estimates a thread's relative "completion time" on each core type and assigns threads to CPU partitions accordingly, using a scalable, lock-light partition scheme (regular + optimistic assignment). Implemented in OpenSolaris and evaluated against a self-implemented dynamic IPC-driven algorithm (Becchi et al.), HASS achieved 7–13% speedups, essentially matching the best static (oracle) assignment, while avoiding the load imbalance and migration overhead that hurt the IPC-driven approach in practice (mainly due to unstable IPC ratios across phase changes). Main limitations: no modeling of shared-cache contention, one static signature per app (no phase-awareness), and reliance on offline profiling/developer cooperation.

- Static vs. dynamic het.-aware scheduling: HASS is a landmark example of a static, signature-based approach (offline profiling) as opposed to dynamic profiling-based schedulers (Becchi et al. [3], Kumar et al. [15]) — useful contrast point if loba uses runtime signals.
- Scalability critique of profiling-based schedulers: sampling-based methods don't scale well to many cores/core types due to unequal fast-core demand for sampling — relevant if you argue for a scalable design.
- Real-system validation matters: HASS's IPC-driven reimplementation showed that phase-aware dynamic algorithms perform much worse on real hardware than in simulation (due to forced-migration overhead and unstable IPC during phase transitions) — good citation for motivating real-system evaluation over simulation.
- Partition-based, lock-scalable architecture: HASS's CPU-partition abstraction with regular/optimistic (swap-based) assignment and per-partition locking is a concrete scalability mechanism worth comparing against your loba design.
- Known gaps HASS leaves open: shared-cache effects, multithreaded/task-level signatures, phase-awareness, priority-awareness — good "future work HASS didn't solve" hooks to position your contribution.

### Bias Scheduling

Bias Scheduling in Heterogeneous Multi-core Architectures (Koufaty, Reddy, Hahn — Intel Labs, EuroSys'10) proposes an OS scheduling technique for performance-asymmetric big/small core systems. Instead of costly CPI sampling on all core types or offline profiling, the authors classify each thread's bias (preference for big vs. small core) using low-overhead performance counters that track internal stalls (core-local resource contention) and external stalls (LLC/memory access). A thread dominated by either stall type gets a small-core bias; one dominated by execution cycles gets a big-core bias. This bias is computed as a running average and used only during load balancing — migrating/swapping threads toward their preferred core type — without touching other scheduler decisions (fairness, priority, when-to-run). Implemented on Linux 2.6.27.5 on a real asymmetric Xeon X5560 platform (one big core + three throttled small cores, "1B3S"), it improved heterogeneous workload performance by ~9–11% on average (up to 20% on a 1B1S config), with minimal (<1%) overhead. The paper also shows DVFS-based emulation of heterogeneity is misleading, since real microarchitectural asymmetry behaves very differently from frequency scaling.

- Online CPI sampling approaches (Kumar et al. [12,13], Becchi & Crowley [3]): dynamically test thread performance by migrating threads across core types and sampling CPI — accurate but expensive due to migration overhead; largely simulation-based.
- Offline profiling (Shelepov et al., HASS [15]): builds static application "signatures" (e.g., cache-miss rates) pre-runtime to guide scheduling; fails to adapt to phase changes or unknown input sets.
- Phase-aware/offline+online hybrid (Sondag et al. [16]): groups similar phases offline, then dynamically matches phases to representative behavior.
- DVFS-based asymmetry modeling (used in prior heterogeneity studies): shown by this paper to be an inaccurate proxy — frequency scaling doesn't reproduce true microarchitectural stall behavior (internal stalls stay constant, differing fundamentally from real asymmetric cores).
- SMT/homogeneous-core phase scheduling (DeVuyst et al. [5], Ghiasi et al. [7]): related techniques for adapting scheduling to execution phases, but on non-heterogeneous or frequency-only asymmetric systems.
- Positioning for [[loba]]: this paper's core contribution — deriving bias from existing low-overhead HW counters (no dedicated sampling runs) and hooking only into load-balancing — is a close conceptual precedent for a load-balancing scheduler on AMP hardware, useful to contrast against your metric design and L4Re implementation choices.

### PIE

Performance Impact Estimation (PIE) (Van Craeynest et al., 2012) tackles core-to-thread mapping on single-ISA heterogeneous multi-cores (big out-of-order + small in-order). Key contributions:

- Motivation: Memory intensity alone is a poor scheduling indicator — some memory-intensive workloads slow down a lot on small cores, others don't; same for compute-intensive workloads. The real drivers are ILP (exploitable by small cores) and MLP (exploitable by big cores).
- PIE model: Uses CPI-stack decomposition (base + memory components) collected on the current core to estimate performance on the other core type, via MLP ratio and ILP ratio formulas — no need to actually sample-run on the other core.
- Hardware cost: Very cheap — five 10-bit counters + 64 bits of dependency-distance tracking.
- Results: ~9–13% average prediction error; dynamic PIE scheduling beats memory-dominance scheduling by 5.5% and sampling-based scheduling by 8.7% (private LLC), with similar gains on shared LLC configs. Scales to multi-core (1 big + N small, or N big + 1 small) configurations.
- Migration overhead: Negligible (<0.6%) with shared LLC at 2.5ms scheduling intervals; private powered-off LLCs are very costly to migrate under.


- Sampling-based scheduling (Becchi & Crowley; Kumar et al.) — runs workload on each core type periodically to measure actual performance; PIE's main point of comparison/improvement, since sampling doesn't scale with core count and incurs migration overhead.
- Memory-dominance / bias scheduling (Koufaty et al.'s "Bias scheduling") — schedules by memory-intensity or stall-cycle heuristics alone; PIE explicitly refutes this as insufficient (Figures 1–2 evidence).
- Static/offline scheduling (HASS — Shelepov et al.; Chen & John) — profile-guided but can't adapt to time-varying phase behavior, unlike PIE's dynamic approach.
- Frequency-scaling heterogeneity (Ghiasi et al.; Shelepov et al.; Srinivasan et al.) — changes clock frequency rather than microarchitecture, sidestepping the ILP/MLP mismatch problem PIE addresses.
- MLP-exploitation mechanisms (Chou et al. on OOO vs in-order MLP; Patsilaras et al. on runahead execution in AMP cores) — foundational for why MLP differs by core type, and an alternative architectural (not scheduling) approach to the same problem.
- Foundational AMP case studies (Kumar et al. 2003/2004, single-ISA heterogeneous multi-core potential) — establishes the energy/performance case for AMP that motivates scheduling research like PIE (and your loba work).

Good contrast case: PIE estimates cross-core performance via CPI/MLP/ILP profiling rather than a simpler preemption-pressure metric like yours, which is a useful point of differentiation to write up explicitly.

## Microkernel Load Balancing

### QNX AMP

In QNX's AMP model, each CPU can run the same OS/version (homogeneous) or a different OS/version (heterogeneous), and this offers a straightforward path for porting legacy uniprocessor code while giving direct control over how each CPU is used. Resource allocation — physical memory, peripherals, interrupt handling — is decided by the developer and normally assigned statically at boot time rather than dynamically, since dynamic allocation would require complex CPU coordination.

Critically for load balancing: in an AMP system a process always runs on the same CPU it started on, even while other CPUs sit idle, which can leave a CPU under- or over-utilized. QNX notes that allowing dynamic migration to fix this would require complex state checkpointing or a service interruption while the process is stopped and restarted on another core, and migration becomes difficult or impossible when the CPUs run different OSs.

In short: QNX AMP has no runtime load balancing at all — CPU assignment is a static, boot-time, developer-controlled decision, and QNX explicitly flags migration as impractical in this model.

Implications for your related work
Strong contrast point, not a competing scheduler: QNX AMP is the "null case" for load balancing — static pinning with no runtime rebalancing — which sharpens the motivation for loba's dynamic approach on AMP/hybrid hardware.
Validates the migration-cost concern: QNX's own stated reasons for avoiding dynamic migration (checkpointing overhead, service interruption) are useful supporting evidence when you justify loba's preemption-pressure metric and migration cost-benefit tradeoffs.
Distinguishes AMP terminology: QNX's "AMP" denotes static CPU-to-process binding (potentially heterogeneous OSes per core), which is a different sense of "asymmetric" than your P/E hybrid-core context — worth clarifying explicitly to avoid terminology confusion with your thesis's use of "AMP."
Adjacent QNX model worth citing too: QNX's BMP (bound multiprocessing) sits between AMP and SMP and may be more directly comparable to loba's approach — worth a look if you want a QNX model that does support some scheduling flexibility.
Industrial/commercial RTOS angle: citing QNX broadens your related work beyond research microkernels (Fiasco.OC/OmniRE, Barrelfish, FOS) to show awareness of production embedded/automotive systems' (non-)treatment of load balancing.

### Global Dynamic Balancing

This paper (Tan et al., ISSSR 2021) presents a centralized, dynamic, global load balancing mechanism for the Mginkgo microkernel (seL4-derived), targeting homogeneous multi-core embedded/IoT devices. Key points:

Motivation: Load balancing research has focused on monolithic kernels (Linux CFS, Android BFS); microkernels are understudied despite growing adoption (HarmonyOS, QNX).
Design: Root-server-centric, three-stage pipeline — load monitoring (per-core load_state_t tracking ready-task time-slice sums), balancing decision (heavy/normal/light classification via a threshold T=20% around average load A), and task migration. Two triggers: on new-task creation (get_free_core()) and periodic timer (get_transfer_task(), every 100ms).
Migration heuristic: picks the smallest time-slice task on the most-loaded core; only migrates if doing so actually improves the max/min balance (avoids just shifting the bottleneck).
Results (i.MX6Q, ARM Cortex-A9, 4 cores): ~4882 cycles (6.16 µs) for task-creation-triggered balancing, ~6596 cycles (8.33 µs) for timer-triggered; ~20% CPU utilization improvement on a 256×256 matrix-multiply workload; load-balancer overhead itself only ~0.0082% CPU.
Related-work points for your thesis
Direct precedent for microkernel-specific load balancing — one of few papers explicitly targeting microkernels rather than monolithic kernels; good contrast point since your loba work also targets microkernel (L4Re) primitives but AMP/hybrid hardware rather than homogeneous cores.
Centralized vs. distributed tradeoff — they adopt centralized (rootserver-based) for simplicity, explicitly naming the bottleneck risk as a known limitation; useful to cite when justifying your own architecture choice (loba's approach, whether centralized or per-CPU).
Load metric: sum of ready-task time-slices as load proxy, with a static heavy/normal/light threshold (T=20%) — worth comparing against your CPU-level preemption pressure metric, since theirs doesn't account for heterogeneous/AMP core capacity differences.
Migration decision heuristic: only migrate if it strictly improves post-migration balance (prevents oscillation) — relevant to cite alongside your own migration-safety design.
Trigger model: dual triggers (event-driven at task creation + periodic timer) — a simple pattern you can contrast with more adaptive/reactive triggering if loba differs.
Evaluation methodology: cycle-accurate PMU measurement of decision-function latency + CPU utilization comparison — a template for how to structure your own benchmarking chapter, though scoped only to homogeneous 4-core ARM, no AMP/heterogeneous evaluation, which is a gap your thesis can highlight.
Limitation they acknowledge: threshold T not empirically tuned, and the rootserver's own core is excluded from balancing — both are open problems you could position loba as addressing.

## L4Re Scheduling

### Omnire

OmniRE (Kuang, Waddington, Tian — Samsung Research, Euro-Par 2013) proposes a scalable replacement personality for L4Re on the Fiasco.OC microkernel. The authors first show that stock L4Re scales poorly on a 48-core AMD server: memory allocation degrades ~89% over 40 cores and thread creation similarly collapses, mainly due to the single-threaded root pager (Sigma0) becoming a contention point and heavy cross-core IPC.

OmniRE's fix is architectural decentralization: an Omni-Core holds the root resource-management tree and delegates coarse-grained quotas to per-core App-Cores, each running its own multithreaded pager, Resource Allocators (per resource type: memory, threads, IPC gates, semaphores, IRQs), and Service Domain Threads. The core design principle is localization — resource management, resource access, and page-fault handling all happen on the same core whenever possible, since cross-core IPC is ~10x slower than same-core IPC. A concrete case study replaces the single global PMA/Sigma0 pager with per-core PMAs and per-core pagers, linked via the kernel's PCB pager field.

Experiments on a 48-core AMD Magnycours and 6-core Intel Xeon show OmniRE stays nearly flat (~5% degradation at 48 cores) versus L4Re's >240% degradation, and OmniRE eventually outperforms Linux page-allocation scaling past ~9 cores, though Linux wins at low core counts due to microkernel IPC overhead.

Key points for your Related Work section
Same substrate, different problem framing: OmniRE targets multicore scalability on L4Re/Fiasco.OC — useful as a scalability-motivated predecessor to loba, but its focus is resource-management contention, not AMP/hybrid-core load balancing.
Root-cause diagnosis you can cite: identifies the single-threaded Sigma0 pager and centralized resource management as the scalability bottleneck in stock L4Re — supports your framing of L4Re's default limitations.
Design principle transferable to loba: core-localization ("keep resource management, access, and fault handling on the same core") and the ~10x same-core vs. cross-core IPC cost — relevant justification for why your scheduler should minimize cross-core migrations/IPC.
Architecture pattern: hierarchical delegation (Omni-Core → App-Cores → per-core Resource Allocators) is a decentralization strategy distinct from your load-balancing approach — good contrast point (static partitioning/quotas vs. your dynamic load-balancing metric).
Not AMP-aware: OmniRE assumes homogeneous multicore (SMP), not asymmetric P/E-core hardware — a clear gap you can position loba against.
Related-work overlaps you may also want to cite: it positions itself against Barrelfish, FOS, Bastei/Genode, K42, and Tessellation — potentially useful pointers for your own related-work net.
Methodology note: uses per-core micro-benchmarks (page alloc/free, thread creation, IPC ping-pong) — could be a benchmarking-methodology reference for your evaluation chapter.

### Thesis Philipp Eppelt

Eppelt's 2016 Diplomarbeit (same TU Dresden chair as yours) builds a user-level load balancer for Fiasco.OC/L4Re, since the kernel only exposes scheduling mechanism, not policy. It uses per-thread hardware performance counters (cycles, instructions, LLC misses — via a kernel extension he added) plus static task config (security/real-time/communication groups) to drive a Measure-Predict-Decide-Enforce cycle. He implements four algorithms — Simple Load Distribution (baseline), Space-Time-Balance, Temporal-only Balance, vs. Linux CFS — and evaluates on SPEC CPU2006 benchmarks (gcc, mcf, gamess, lbm) on a homogeneous Haswell SMT machine. Result: CFS is usually fastest, SLD is fast solo but unpredictable under load, and his behavior-aware algorithms (esp. STB) win on fairness/low run-time deviation under load rather than raw speed. He flags heterogeneous/AMP hardware as unaddressed future work.

Key points for your Related Work section:

Direct predecessor: same kernel, same "mechanism not policy" scheduler gap — good continuity framing.
Core differentiator: his SMT abstraction problem (logical vs. physical symmetric cores) is analogous but distinct from your AMP problem (fundamentally heterogeneous cores) — his load metrics (IPC, MPC, exec time) assume core equivalence once HT-normalized, which breaks under AMP.
He explicitly names heterogeneous/big.LITTLE as future work and cites Sarma et al.'s SmartBalance as the closest existing heterogeneous-aware scheduler — cite both as your motivation.
Reusable methodological elements to reference or diverge from: the MPDE cycle decomposition, static isolation/communication group config, and his SPEC-based solo/concurrent/heavy-load evaluation methodology.
His finding that fairness/low-deviation (not median throughput) is where behavior-awareness wins is a useful framing parallel if your AMP scheduler's benefit is similarly about matching threads to appropriate core types.
Other prior work he surveys, worth citing directly if relevant: Snavely & Tullsen (symbiotic SMT scheduling), Zhuravlev et al. (contention-aware DI/DIO), Knauerhase et al. (cache-weight balancing), Hofmeyr et al. (speed balancing).

## Content

General Purpose Operating System Scheduling

Linux CFS

Load computed as thread weight × CPU utilization ÷ cgroup size, not simple thread counts
Balances hierarchically (SMT → cache domains → NUMA) via periodic checks, idle cores, and thread wake/create events
One designated core per domain migrates up to 32 threads at a time between busiest/idlest groups
Uses imbalance thresholds (25%+ for distant NUMA nodes) and cache-locality heuristics to limit unnecessary migration

Windows

Pull-based: idle processors search for work rather than busy ones pushing it away
Thread placement uses a hierarchical fallback (ideal → last → current → same-SMT-set → lowest-numbered processor) to preserve cache locality
NUMA- and SMT-aware; migrates proactively at quantum-end if a thread's SMT partner core is busy while others sit idle
No periodic rebalancing — migration only on-demand when placement logic finds a better core

Framing for loba: both are mechanism-rich, homogeneous-hardware baselines against which you can contrast an AMP-native design built from L4Re primitives rather than retrofitted onto an existing balancer.

AMP Aware Balancing

AMPS (Intel, SC'07) — minimal patch to Linux's find_busiest_group()/load metric: scales core load by compute power, keeps fast cores populated first, and gates migrations by NUMA/cache-miss cost prediction. Good contrast if loba is more architectural/from-scratch; its scaled-load metric is a direct precursor worth citing against your preemption-pressure metric.

HASS (OpenSolaris) — static, offline-profiled "architectural signatures" instead of online monitoring; matches threads to core types via predicted completion time. Matches oracle performance but ignores shared-cache contention and phase changes. Useful static-vs-dynamic contrast if loba uses runtime signals; also a citation for why sampling-based approaches don't scale.

Bias Scheduling (Intel Labs, EuroSys'10) — classifies thread "bias" (big vs. small core preference) from cheap existing HW counters (internal vs. external stalls), applied only during load balancing. Close conceptual precedent for loba's low-overhead-metric approach; also shows DVFS-based heterogeneity emulation is misleading (relevant if you justify testing on real/simulated AMP hardware).

PIE (2012) — predicts cross-core performance via CPI-stack/MLP/ILP estimation rather than sampling; very cheap HW cost, beats bias- and sampling-based scheduling. Strong contrast case: PIE's estimation-heavy model vs. your simpler preemption-pressure metric is worth stating explicitly.

Microkernel Load Balancing

QNX AMP — no runtime load balancing at all; CPU-to-process binding is static and boot-time. Explicitly calls dynamic migration impractical due to checkpointing/interruption cost. Use as the "null case" that sharpens loba's motivation, and note QNX's different sense of "AMP" (potentially different OSes per core) to avoid terminology confusion with your P/E hybrid-core usage.

Global Dynamic Balancing (Mginkgo/seL4-derived, ISSSR 2021) — centralized, rootserver-based balancer for homogeneous microkernel cores; load = summed ready-task time-slices vs. a static 20% threshold; dual triggers (task creation + 100ms timer); migrates only if it strictly improves balance. One of few microkernel-specific balancers — good direct precedent, but homogeneous-only (no AMP), which is a gap you can highlight. Also useful as an evaluation-methodology template (cycle-accurate PMU measurement).

L4Re Scheduling

OmniRE (Samsung, Euro-Par 2013) — diagnoses L4Re/Fiasco.OC's poor 48-core scalability (single-threaded Sigma0 pager, cross-core IPC ~10x same-core cost) and fixes it via decentralized per-core resource management (Omni-Core → App-Cores). Relevant for: (1) justifying L4Re's default limitations, (2) the core-localization principle motivating minimal cross-core migration in loba, (3) a clear "not AMP-aware, SMP-only" gap to position against.

Eppelt Thesis (2016, same TU Dresden chair) — direct predecessor: user-level load balancer for Fiasco.OC/L4Re using HW performance counters + static task config in a Measure-Predict-Decide-Enforce cycle; tested 4 algorithms against CFS on homogeneous Haswell SMT. Findings: CFS fastest overall, his behavior-aware algorithms win on fairness/low deviation, not raw speed. Explicitly flags heterogeneous/AMP hardware as unaddressed future work — direct continuity point for loba, and his fairness-over-throughput framing may parallel how you argue loba's benefit.