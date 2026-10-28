# Hardware Registry

Records host hardware profiles and GPU capabilities across team machines.

---

## Machine Profiles

### Machine B (Hub / Backend / LLM)
* **Role**: Backend Hub (`:8000`), SQLite (WAL), Ollama (`:11434`)
* **Hardware Specs**: NVIDIA GeForce RTX 3050 Laptop GPU (4096 MiB VRAM), Driver 616.56, CUDA 13.4
* **`nvidia-smi` output**:
```text
Wed Oct 28 15:29:55 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 616.56                 KMD Version: 616.56        CUDA UMD Version: 13.4     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                  Driver-Model | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 3050 ...  WDDM  |   00000000:01:00.0 Off |                  N/A |
| N/A   49C    P0              8W /   75W |       0MiB /   4096MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+
```

---

### Machine A (ML / Image Pipeline)
* **Role**: ML Service (`:8001`)
* **Hardware Specs**: Pending
* **`nvidia-smi` output**:
```text
[Pending: to be appended by Person A]
```

---

### Machine C (Frontend / Speech Service)
* **Role**: Frontend (`:5173`), Speech Service (`:8002` on CPU for dev)
* **Hardware Specs**: Pending
* **Specs output**:
```text
[Pending: to be appended by Person C]
```
