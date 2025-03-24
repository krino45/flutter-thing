import os
import numpy as np
import pyNastran.f06.parse_flutter as fl
import matplotlib.pyplot as plt


def get_flutter(input_file_name, input_dir):
    """
    Get flutter analysis results for the specified file
    
    Parameters:
    input_file_name (str): Name of the F06 file
    input_dir (str): Directory containing the file
    
    Returns:
    tuple: (velocities, frequencies, dampings, roots)
    """
    # Reading results
    input_path_file = os.path.abspath(os.path.join(input_dir, input_file_name))
    if not os.path.isfile(input_path_file):
        raise Exception(f"Could not find the file: {input_path_file}")
        
    flutters = fl.make_flutter_response(input_path_file, f06_units="si", out_units="si")
    response = flutters[list(flutters)[0]]

    # Prepare data by modes
    num_modes, num_steps, num_columns = response.results.shape
    velocities = np.zeros(num_steps)
    dampings = np.zeros([num_steps, num_modes])
    frequencies = np.zeros([num_steps, num_modes])
    
    for i_mode in range(num_modes):
        for i_step in range(num_steps):
            velocities[i_step] = response.results[i_mode, i_step, 2]
            frequencies[i_step, i_mode] = response.results[i_mode, i_step, 4]
            dampings[i_step, i_mode] = response.results[i_mode, i_step, 3]

    # Find roots
    roots = dict()
    for i_mode in range(num_modes):
        mode_damping = dampings[:, i_mode]
        mode_roots = np.array([])
        for i_step in range(num_steps - 1):
            fa = mode_damping[i_step]
            fb = mode_damping[i_step + 1]
            if fa * fb < 0:
                a = velocities[i_step]
                b = velocities[i_step + 1]
                root = fa / (fa - fb) * (b - a) + a
                mode_roots = np.append(mode_roots, root)
        roots[i_mode] = mode_roots

    return velocities, frequencies, dampings, roots


def write_roots(input_file_name, output_dir, roots):
    """
    Write flutter roots to a text file
    
    Parameters:
    input_file_name (str): Name of the input F06 file
    output_dir (str): Directory to save the output file
    roots (dict): Dictionary of flutter roots by mode
    """
    name = os.path.splitext(os.path.basename(input_file_name))[0]
    output_file_name = f"{name}.txt"
    output_path_file = os.path.join(output_dir, output_file_name)
    
    num_modes = len(roots)
    with open(output_path_file, "w") as file:
        for i_mode in range(num_modes):
            values = roots[i_mode]
            if values.size > 0:
                header = f"Mode {i_mode+1:2d}: "
                data = ", ".join([f"{x:.3f}" for x in values])
                line = header + data
                print(line)
                file.write(line + "\n")


def plot_vg(flow, freqs, deltas, modes=[], name="V-g Diagram"):
    """
    Create a V-g diagram plot
    
    Parameters:
    flow (ndarray): Array of flow velocities
    freqs (ndarray): Array of frequencies by mode
    deltas (ndarray): Array of damping values by mode
    modes (list): List of modes to plot (empty for all)
    name (str): Title of the plot
    
    Returns:
    matplotlib.figure.Figure: The created figure
    """
    fig = plt.figure()
    axes = fig.subplots(nrows=2, ncols=1)
    num_modes = freqs.shape[1]
    
    if not modes:
        modes = range(0, num_modes)

    # Plot damping
    for j in modes:
        axes[0].plot(flow, deltas[:, j], label=f"{j+1}", marker=".")
    axes[0].set_title(name)
    axes[0].set_ylabel("Log. Decrement")
    axes[0].grid(True)

    # Plot frequencies
    for j in modes:
        axes[1].plot(flow, freqs[:, j], label=f"{j+1}", marker=".")
    axes[1].set_xlabel("Flow Velocity, m/s")
    axes[1].set_ylabel("Frequency, Hz")
    axes[1].grid(True)

    # Add legend
    lines, labels = axes[0].get_legend_handles_labels()
    fig.legend(lines, labels, loc="upper right")
    plt.subplots_adjust(right=0.85)
    
    return fig


if __name__ == "__main__":
    # Standalone execution for testing
    input_dir = "./input"
    output_dir = "./output"
    modes = []
    
    for input_file_name in os.listdir(input_dir):
        if input_file_name.lower().endswith('.f06'):
            velocities, frequencies, dampings, roots = get_flutter(input_file_name, input_dir)
            write_roots(input_file_name, output_dir, roots)
            plot_vg(velocities, frequencies, dampings, modes, input_file_name)
    
    plt.show()