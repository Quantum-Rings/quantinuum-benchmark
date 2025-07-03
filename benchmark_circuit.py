from platform import python_version
print(python_version())
import os
import sys
sys.stdout.reconfigure(line_buffering=True) # Prevent buffering when running with nohup
import QuantumRingsLib
from QuantumRingsLib import QuantumRegister, AncillaRegister, ClassicalRegister, QuantumCircuit
from QuantumRingsLib import QuantumRingsProvider
from QuantumRingsLib import job_monitor
from QuantumRingsLib import JobStatus
from QuantumRingsLib import OptimizeQuantumCircuit
from matplotlib import pyplot as plt
import numpy as np
import math
import time
from collections import Counter
import json
import csv
from pathlib import Path
import subprocess

DEFAULT_CONFIG = {
    "system_state_path": None,
    "json_file": None,
    "pytket_circuit_path": None,
    "pytket_dagger_path": None,
    "transpiled_circuit_path": None,
    "transpiled_dagger_path": None,
    "results_path": None,
    "token": None,
    "email":None,
    "python_bin": "python",
    "transpile_script": "transpile_pytket.py",
}

def list_circuit_files(circuit_path):
    try:
        return [f for f in os.listdir(circuit_path) if f.endswith(".json")]
    except FileNotFoundError:
        return []

def print_usage(config):
    dummy_provider = QuantumRingsProvider()
    backends = dummy_provider.backends()
    print(backends)

    print("Usage:")
    print(f"  {config['python_bin']} {Path(__file__).name} <backend_index> <circuit_file_name> <gpu_index> [threshold] [--key=value ...]\n")
    print("Available Backends:")
    for i, b in enumerate(backends):
        print(f"  {i}: {b}")
    print("\nAvailable Circuit Files:")
    for f in list_circuit_files(config['pytket_circuit_path']):
        print(f"  {f}")
    print("\nOptional config overrides:")
    for key in DEFAULT_CONFIG:
        print(f"  --{key}=<value> (default: {config[key]})")
    sys.exit(1)

def parse_optional_args(config, args):
    for arg in args:
        if arg.startswith("--"):
            key_value = arg[2:].split("=", 1)
            if len(key_value) == 2 and key_value[0] in config:
                config[key_value[0]] = key_value[1]
            else:
                print(f"Warning: Ignored unknown or malformed option '{arg}'")
    return config

def write_csv_line(filename, row, mode='a'):
    """
    Writes a single row to a CSV file.

    Args:
        filename (str): The name of the CSV file.
        row (list or tuple): The data to write as a single row.
        mode (str, optional): The file opening mode ('w' for write, 'a' for append).
            Defaults to 'a'.  Use 'w' for the first line (or to overwrite).
    """
    with open(filename, mode, newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(row)

def save_partial_results(state_dir, circuit_name, data):
    filename = Path(state_dir) / f"{circuit_name}_partial_results.json"
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def load_partial_results(state_dir, circuit_name):
    filename = Path(state_dir) / f"{circuit_name}_partial_results.json"
    if not filename.exists():
        return None  # No saved state
    with open(filename, "r") as f:
        return json.load(f)

def setup():
    if len(sys.argv) < 4:
        print("Error: Missing required arguments.\n")
        print_usage(DEFAULT_CONFIG)

    config = DEFAULT_CONFIG.copy()

    # Split args
    positional_args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    optional_args = [arg for arg in sys.argv[1:] if arg.startswith("--")]
    config = parse_optional_args(config, optional_args)

    # Validate that all required config keys are defined
    missing_keys = [key for key, val in config.items() if val is None and key != "python_bin"]
    if missing_keys:
        print("Error: Missing required config values.\n")
        for key in missing_keys:
            print(f"  --{key}=<value>  (currently missing)")
        print("")
        print_usage(config)

    provider = QuantumRingsProvider(token=config["token"], name=config["email"])
    backends = provider.backends()

    # Parse backend index
    try:
        backend_index = int(positional_args[0])
        backend = backends[backend_index]
    except (ValueError, IndexError):
        print("Error: Invalid backend index.\n")
        print_usage(config)

    # Parse circuit name
    circuit_name = positional_args[1]
    if circuit_name not in list_circuit_files(config['pytket_circuit_path']):
        print(f"Error: Circuit file '{circuit_name}' not found in {config['pytket_circuit_path']}.\n")
        print_usage(config)

    # Parse GPU index
    try:
        gpu_index = int(positional_args[2])
    except ValueError:
        print("Error: GPU index must be an integer.\n")
        print_usage(config)

    # Optional threshold
    threshold = None
    if len(positional_args) > 3:
        try:
            threshold = int(positional_args[3])
        except ValueError:
            print("Error: Threshold must be an integer.\n")
            print_usage(config)

    # Print summary
    print(f"Backend: {backend}")
    print(f"Circuit file: {circuit_name}")
    print(f"GPU index: {gpu_index}")
    print(f"Threshold: {threshold if threshold is not None else '(default)'}")
    print("\nConfiguration paths:")
    for k, v in config.items():
        print(f"  {k}: {v}")

    dagger_circuit_name = os.path.join(config['pytket_dagger_path'], circuit_name)
    if not os.path.exists(dagger_circuit_name):
        print(f"Dagger Circuit {dagger_circuit_name} is not existing. We will not be able to calculate Mirror Fidelity")

    try:
        with open(config['json_file'], 'r') as f:
            exp_data = json.load(f)
        print("JSON data loaded successfully.")

    except FileNotFoundError:
        print(f"Error: The file '{config['json_file']}' was not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON in '{config['json_file']}': {e}")
        sys.exit(1)

    return config, provider, backends, backend_index, circuit_name, gpu_index, threshold, exp_data

def now():
    return time.time_ns() / (10 ** 9)

def main():
    config, provider, backends, backend_index, circuit_name, gpu_index, threshold, exp_data = setup()

    stripped_circuit_name = Path(circuit_name).stem
    system_state_path = Path(config['system_state_path'])
    system_state_file = str(Path(system_state_path) / f"{stripped_circuit_name}.bin")
    pytket_circuit_path = config['pytket_circuit_path']
    pytket_dagger_path = config['pytket_dagger_path']
    transpiled_circuit_path = config['transpiled_circuit_path']
    transpiled_dagger_path = config['transpiled_dagger_path']
    results_path = config['results_path']
    csv_file = Path(results_path) / f"{stripped_circuit_name}.csv"
    shots_output_file = Path(results_path) / f"{stripped_circuit_name}.shots.txt"
    exp_output_file = Path(results_path) / f"{stripped_circuit_name}.exp.json"

    backend = provider.get_backend(backends[backend_index], gpu=gpu_index)

    print("Account Name: ", provider.active_account()["name"], "\nMax Qubits: ", provider.active_account()["max_qubits"])

    partial_data = load_partial_results(system_state_path, stripped_circuit_name)

    if partial_data:
        print(f"Skipping steps 1–3 for {stripped_circuit_name}, using cached partial results.")
        expectation_value_time = partial_data["expectation_value_time"]
        threshold = partial_data["threshold"]
        backend_index = partial_data["backend_index"]

        transpiling_time = partial_data["transpiling_time"]
        pre_processing_time = partial_data["pre_processing_time"]
        state_preparation_time = partial_data["state_preparation_time"]
        total_prep_time = partial_data["total_prep_time"]
        final_state_memory = partial_data["final_state_memory"]

    else:
        print("\nSTEP 0: Transpiling")

        start_time = now()

        transpile_circuit_result = subprocess.run([
                config['python_bin'], 
                config['transpile_script'],
                stripped_circuit_name,
                pytket_circuit_path,
                transpiled_circuit_path
            ], capture_output=True, text=True)
        print(f"Isolated script output:\n{transpile_circuit_result.stdout}")
        if(transpile_circuit_result.stderr):
            print(f"Isolated script errors:\n{transpile_circuit_result.stderr}")

        if transpile_circuit_result.returncode != 0:
            print("Error: Transpilation subprocess failed.")
            sys.exit(1)

        dagger_circuit_path = Path(config["pytket_dagger_path"]) / circuit_name
        if dagger_circuit_path.exists():
            transpile_dagger_result = subprocess.run([
                    config['python_bin'], 
                    config['transpile_script'],
                    stripped_circuit_name,
                    pytket_dagger_path,
                    transpiled_dagger_path
                ], capture_output=True, text=True)
            print(f"Isolated script output:\n{transpile_dagger_result.stdout}")
            if(transpile_dagger_result.stderr):
                print(f"Isolated script errors:\n{transpile_dagger_result.stderr}")

            if transpile_dagger_result.returncode != 0:
                print("Error: Transpilation subprocess failed.")
                sys.exit(1)

        end_time = now()

        transpiling_time = end_time - start_time

        print(f"Transpiling time: {transpiling_time}")

        transpiled_circuit_file = Path(transpiled_circuit_path) / f"{stripped_circuit_name}.qasm"

        if not Path(transpiled_circuit_file).exists():
            print(f"Error: Transpiled circuit {transpiled_circuit_file} not found.")

        print("\nSTEP 1: Pre-Processing")

        total_prep_start_time = now()

        start_time = now()

        qc1 = QuantumCircuit.from_qasm_file(str(transpiled_circuit_file))

        OptimizeQuantumCircuit(qc1)

        end_time = now()

        pre_processing_time = end_time - start_time

        print("Number of Qubits: ", qc1.num_qubits)
        gate_counts = qc1.count_ops()
        print(f"Circuit operations: {gate_counts}")
        total_count = sum(gate_counts.values())

        print(f"Total number of gate operations: {total_count}")

        print(f"Pre-processing time: {pre_processing_time}")

        print("\nSTEP 2: State Preparation")

        number_of_shots = 1
        start_time = now()

        if threshold is not None:
            job = backend.run(qc1, shots=number_of_shots, mode="sync", generate_amplitude = False, quiet=True, performance="custom", threshold=threshold)
        else:
            job = backend.run(qc1, shots=number_of_shots, mode="sync", performance = "balancedAccuracy", generate_amplitude = False, quiet=True)

        job_monitor(job, quiet=True)
        end_time = now()

        state_preparation_time = end_time - start_time

        print(f"Initial State Preparation Time taken: {state_preparation_time} seconds")

        result = job.result()

        result.SaveSystemStateToDiskFile(system_state_file)
        print("State Preparation: Time taken: ", end_time - start_time, "seconds.")

        final_state_memory = os.path.getsize(system_state_file)/1024/1024
        print("Final State Memory: ", final_state_memory, "MB")

        print("\nSTEP 3: Pauli Expectation Value")

        average_expectation_value = 0
        expectation_values = []

        if stripped_circuit_name in exp_data.keys():
            qubit_list = list(range(qc1.num_qubits))
            exp_values = exp_data[stripped_circuit_name]

            print("Pauli Operators:")
            exp_sum = 0
            expectation_values = []

            start_time = now()

            for exp_value in exp_values:
                reversed = exp_value[::-1]

                exp_val = result.get_pauliexpectationvalue(reversed, qubit_list, 0, 0)
                expectation_value = exp_val.real

                exp_values[exp_value] = str(expectation_value)
                print("Expectation Value for ", exp_value, " = ", expectation_value)

                exp_sum += expectation_value

            average_expectation_value = exp_sum / len(exp_values)

            end_time = now()
        
            expectation_value_time = end_time - start_time

            print(f"Average Expectation Value = {average_expectation_value}")
            print(f"Expectation Value Calculation Time taken: {expectation_value_time} seconds")

            exp_out = {}
            exp_out[stripped_circuit_name] = exp_values
            with open(exp_output_file, 'w') as f:
                json.dump(exp_out, f, indent=4)
            print("Expectation values written to: ", exp_output_file)

        else:
            print(f"Pauli operator for circuit {stripped_circuit_name} is not found.")
            expectation_value_time = 0

        total_prep_end_time = now()
        total_prep_time = total_prep_end_time - total_prep_start_time

        save_partial_results(system_state_path, stripped_circuit_name, {
            "circuit_name": stripped_circuit_name,
            "expectation_value_time": expectation_value_time,
            "threshold": threshold,
            "backend_index": backend_index,
            "transpiling_time": transpiling_time,
            "pre_processing_time": pre_processing_time,
            "state_preparation_time": state_preparation_time,
            "total_prep_time": total_prep_time,
            "final_state_memory": final_state_memory,
        })

    print("\nSTEP 4: First 100 shots:")

    total_runtime_start_time = now()

    start_time = now()

    qc1 = QuantumCircuit(simulation_state_file = system_state_file)
    qc1.measure_all()
    number_of_shots = 100

    if threshold is not None:
        job = backend.run(qc1, shots=number_of_shots, mode="sync", generate_amplitude = False, quiet=True, performance="custom", threshold=threshold)
    else:
        job = backend.run(qc1, shots=number_of_shots, mode="sync", performance = "balancedAccuracy", generate_amplitude = False, quiet=True)

    job_monitor(job, quiet=True)

    result = job.result()
    shots = result.get_memory()

    with open(shots_output_file, "w") as f:
        for i in range(len(shots)):

            reversed_sample = shots[i][::-1]
            f.write(reversed_sample + "\n")

    print("Shots written to: ", shots_output_file)

    end_time = now()

    shots_time = end_time - start_time

    print(f"First 100 Shots Time taken: {shots_time}")

    print("\nSTEP 6: Mirror Fidelity")

    mirror_fidelity = -1
    mirror_fidelity_time = 0

    dagger_circuit_file = Path(transpiled_dagger_path) / f"{stripped_circuit_name}.qasm"

    if dagger_circuit_file.exists():
        qc1 = QuantumCircuit(simulation_state_file = system_state_file)
        qc2 =  QuantumCircuit.from_qasm_file(str(dagger_circuit_file))
    
        num_qubits = qc1.num_qubits
        num_clbits = qc1.num_clbits

        print("Number of qubits: ", num_qubits)
        gate_counts = qc2.count_ops()
        print(f"Circuit operations: {gate_counts}")
        total_count = 0
        for gate, count in gate_counts.items():
            total_count += count

        print(f"Total number of gate operations in dagger circuit: {total_count}\n")

        if (num_qubits != qc2.num_qubits):
            print("Mismatch in the number of qubits between the circuit and its dagger")
        else:
            if (num_clbits != qc2.num_clbits):
                print("Mismatch in the number of classical bits between the circuit and its dagger")
            else:
                qc1.append(qc2)

                number_of_shots = 1
                start_time = now()

                if threshold is not None:
                    job = backend.run(qc1, shots=number_of_shots, mode="sync", generate_amplitude = False, quiet=True, performance="custom", threshold=threshold)
                else:
                    job = backend.run(qc1, shots=number_of_shots, mode="sync", performance = "balancedAccuracy", generate_amplitude = False, quiet=True)

                job_monitor(job, quiet=True)
                end_time = now()

                result = job.result()
                mirror_fidelity = result.get_fidelity()
                print(f"\nMirror Circuit Fidelity:  {mirror_fidelity}")
                mirror_fidelity_time = end_time - start_time
                print(f"Mirror Fidelity Time taken: {mirror_fidelity_time}")

    total_runtime_end_time = now()

    total_runtime = transpiling_time + pre_processing_time + state_preparation_time + shots_time
    other_time = (total_runtime_end_time - total_runtime_start_time) + total_prep_time - (total_runtime + expectation_value_time)

    with open(csv_file, "w", newline="") as csvfile:
        fieldnames = ["circuit_name", "mirror_fidelity", "fidelity_estimate", "total_runtime", "simulation_time", "preprocessing_time", "shot_time", "expectation_value_time", "other_time", "final_state_memory"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "circuit_name": stripped_circuit_name,
            "mirror_fidelity": "" if mirror_fidelity == -1 else mirror_fidelity,
            "fidelity_estimate": "",
            "total_runtime": total_runtime,
            "simulation_time": state_preparation_time,
            "preprocessing_time": transpiling_time + pre_processing_time,
            "shot_time": shots_time,
            "expectation_value_time": expectation_value_time,
            "other_time": other_time,
            "final_state_memory": final_state_memory
        })

    print(f"Done processing {circuit_name}\n\n")

if __name__ == "__main__":
    main()
