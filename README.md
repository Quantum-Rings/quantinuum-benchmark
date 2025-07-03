# Quantum Circuit Runner

`benchmark_circuit.py`. This script runs a quantum circuit simulation using the QuantumRings platform. It supports selecting the backend, GPU index, circuit file, and runtime behavior using command-line arguments.

## 📦 Requirements

- Your circuit files must be available in the directory specified by `pytket_circuit_path`.
- The `json_file` should contain a dictionary of expected Pauli operator measurements (e.g. for fidelity estimation).
- The `transpile_pytket.py` script must exist in the same directory and support command-line arguments for circuit transpilation.

### Required Packages

- `requirements.txt` contains the base packages needed
- Version 0.11.x of the Quantum Rings SDK to be used for the benchmarking. This will be released to the public shortly.

## 🔧 Default Configuration

The following keys can be overridden using `--key=value` arguments. All keys are required unless otherwise noted:

| Key                       | Description                                     | Default                     |
|---------------------------|-------------------------------------------------|-----------------------------|
| `system_state_path`       | Directory to save simulation state files        | `None` (must override)      |
| `json_file`               | Pauli expectation input JSON file               | `None` (must override)      |
| `pytket_circuit_path`     | Input directory for original circuits           | `None` (must override)      |
| `pytket_dagger_path`      | Input directory for dagger circuits             | `None` (must override)      |
| `transpiled_circuit_path` | Output directory for transpiled circuits        | `None` (must override)      |
| `transpiled_dagger_path`  | Output directory for transpiled dagger circuits | `None` (must override)      |
| `results_path`            | Directory where CSV and logs will be written    | `None` (must override)      |
| `token`                   | QuantumRings API token                          | `None` (must override)      |
| `email`                   | QuantumRings account email                      | `None` (must override)      |
| `python_bin`              | Python interpreter to run subprocesses          | `python`                    |
| `transpile_script`        | Script used to transpile circuits               | `transpile_pytket.py`       |

## 🚀 Usage

```bash
python benchmark_circuit.py <backend_index> <circuit_file_name> <gpu_index> [threshold] [--key=value ...]
```

## Example

```bash
python benchmark_circuit.py 0 bell_circuit.json 1 --results_path=/tmp/results \
  --json_file=exp.json --system_state_path=/tmp/state \
  --pytket_circuit_path=./input --pytket_dagger_path=./dagger_input \
  --transpiled_circuit_path=./transpiled --transpiled_dagger_path=./dagger_transpiled \
  --token=abc123 --email=you@example.com
```

## Thresholds

`circuit_list.json` contains threshold values used when running the benchmarks, for example:

```bash
#!/bin/bash

JSON_FILE="circuits_with_thresholds.json"

# Load and loop through each item in the JSON array
jq -c '.[]' "$JSON_FILE" | while read -r item; do
    name=$(echo "$item" | jq -r '.name')
    threshold=$(echo "$item" | jq -r '.threshold')

    echo "Running benchmark for circuit: $name with threshold: $threshold"

    python benchmark_circuit.py 0 "$name.json" 1 \
      --results_path=/tmp/results \
      --json_file=exp.json \
      --system_state_path=/tmp/state \
      --pytket_circuit_path=./input \
      --pytket_dagger_path=./dagger_input \
      --transpiled_circuit_path=./transpiled \
      --transpiled_dagger_path=./dagger_transpiled \
      --token=abc123 \
      --email=you@example.com
done
```