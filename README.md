# Multi-Agent Waste Collection

This project implements a **Multi-Agent Waste Collection System** using SPADE (Smart Python Agent Development Environment). It simulates an intelligent waste management system with autonomous agents representing waste bins and collection trucks that collaborate to optimize waste collection routes and efficiency.

This assignment was developed for the Introduction to Intelligent and Autonomous Systems course (BSc in Artificial Intelligence and Data Science, University of Porto, 2025/2026).

The system features:
- **Bin Agents**: Autonomously manage waste accumulation and send collection requests
- **Truck Agents**: Optimize routes, collaborate with each other, and handle task allocation
- **Dynamic Environment**: Support for traffic conditions, roadblocks, and emergency scenarios
- **Contract Net Protocol**: Bins use CFP (Call For Proposal) to request the best truck for collection
- **Collaborative Problem-Solving**: Trucks assist each other during breakdowns and overload situations
- **Real-time Visualization**: Interactive interface to monitor the simulation

## Authors

- Carolina Proença
- Eduarda Neves
- Maria Morais

## Installation

### Prerequisites
- **Python 3.7+** installed on your system
- A virtual environment (recommended)
- Dependencies of the project: requirements.txt

### Setup Steps

1. **Clone or download the repository**

2. **Create and activate a virtual environment**
   ```bash
   # On Linux/MacOS:
   python3 -m venv venv
   source venv/bin/activate
   
   # On Windows:
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the SPADE backend**
   ```bash
   spade run
   ```
   Keep this terminal open while running the simulation.

## Usage

### Running the Simulation

1. **Start the interface**
   ```bash
   python3 interface.py
   ```

2. **Choose a mode**
   - **Manual Mode**: Manually place bins, trucks, roadblocks, and set traffic levels
   - **Layout Mode**: Load a pre-configured scenario from the `configs/` folder

3. **Load a Configuration** (Layout Mode only)
   ```
   configs/config1.json
   ```

4. **Start the Simulation**
   Click the **Start** button to begin the waste collection simulation.

### Controls

|       Key       |        Action          |
|-----------------|------------------------|
| **B** + Click   | Place Organic Bin      |
| **N** + Click   | Place Recyclable Bin   |
| **T** + Click   | Place Organic Truck    |
| **Y** + Click   | Place Recyclable Truck |
| **R** + Click   | Add/Remove Roadblock   |
| **S**           | Start System           |
| **1-5**         | Set Traffic Level      |
| **0**           | Reset Traffic          |
| **Mouse Wheel** | Scroll the interface   |

## Project Structure

```
Multi-Agent-Waste-Collection/
├── __pycache__/
├── .vscode/
├── configs/
│   ├── config1.json
│   ├── config2.json
│   ├── config3.json
│   ├── config4.json
│   └── config5.json
├── documented/
│   ├── bin_agent.html
│   ├── environment.html
│   ├── index.html
│   ├── interface.html
│   ├── search.js
│   └── truck_agent.html
├── Images/
├── results/
│   ├── results_config1.txt
│   ├── results_config2.txt
│   ├── results_config3.txt
│   ├── results_config4.txt
│   └── results_config5.txt
├── bin_agent.py
├── environment.py
├── interface.py
├── ISIA 2025-2026 - Assignment1.pdf  # Assignment
├── presentation.pdf                  # Presentation slides
├── README.md
├── README.txt                        # Developed for the assignment submission 
├── requirements.txt
└── truck_agent.py
```

## Core Components

### Bin Agent (`bin_agent.py`)
Represents waste bins that:
- Autonomously accumulate waste over time
- Send CFP messages to trucks when waste reaches certain levels
- Accept proposals from trucks and negotiate collection
- Track collection statistics (CFP vs. autonomous collections)
- Handle emergency scenarios

### Truck Agent (`truck_agent.py`)
Represents waste collection vehicles that:
- Explore the environment and identify available bins
- Respond to CFP proposals from bins
- Optimize collection routes using shortest path algorithms
- Manage fuel levels and load capacity
- Collaborate with other trucks for breakdowns or overload situations
- Send collection claims to prevent bin conflicts

### Environment (`environment.py`)
Manages the simulation world:
- Grid-based representation of the city
- Graph structure for pathfinding
- Traffic simulation
- Roadblock management
- Agent state tracking and updates
- System statistics and metrics

### Interface (`interface.py`)
Provides real-time visualization:
- Interactive grid display
- Agent status panels
- Real-time metrics (fuel, load, time)
- Configuration management
- Results export to text files

## Results

The `results/` folder contains simulation statistics including:
- Waste collection efficiency metrics
- CFP response times
- Truck performance (fuel consumption, distance traveled)
- Collaboration statistics
- System performance summaries

Example output from simulations can be viewed in `results_config*.txt` files.

## Documentation

Generated HTML documentation for all components is available in the `documented/` folder. Start with `index.html` to access the rest of the documented files.

## Technologies Used

- **SPADE**: Smart Python Agent Development Environment
- **Pygame**: For GUI rendering
- **NetworkX**: For graph-based pathfinding
- **Tkinter**: For dialog boxes and interface elements
- **Python 3**: Core programming language