import spade
import random
import asyncio
from spade.agent import Agent


from spade.behaviour import PeriodicBehaviour, CyclicBehaviour, OneShotBehaviour
from spade.message import Message
import ast

class BinAgent(spade.agent.Agent):
    """
    An intelligent agent representing an urban waste bin.

    Attributes:
        jid (str): The agent's JID.     
        position (tuple): The (x, y) coordinates of the bin.    
        waste_type (str): The type of waste (organic/recyclable).   
        max_capacity (int): The maximum capacity of the bin.    
        current_waste (int): The current waste level.   
        environment (Environment): The shared simulation environment.   
        received_responses (dict): Stores proposals received from trucks (CFP).         
        accumulation_period (int): Time interval (in seconds) for waste accumulation simulation.          
        is_waiting_for_truck (bool): True if an acceptance message was sent and the bin awaits collection.          
        sent_colection_request (bool): True if a CFP message has been sent.             
        resolving (int): Counter used during problem resolution to check if a peer truck responded.             
        collection_time (list[float]): List of time durations (in seconds) between request and collection (CFP only).         
        counter (int): Counter used in WasteAccumulationBehaviour.          
        overflow_times (list[float]): List of timestamps when the bin reached maximum capacity (overflow).            
        is_overflowing (bool): True if current_waste reached max_capacity.          
        request_start_time (float | None): Timestamp when the collection request (CFP) was sent.        
        total_collections (int): Total number of recorded collections (CFP + Autonomous).       
        cfp_collections (int): Total number of collections initiated via the CFP protocol.      
        autonomous_collections (int): Total number of autonomous collections by trucks.         
        last_collection_type (str | None): Type of the last recorded collection ('cfp' or 'autonomous').        
        collection_counted (bool): Flag to prevent double counting a collection event during monitoring.        
        last_waste_level (int): Stores the waste level from the previous cycle to detect collection events.         
    """
    
    def __init__(self, jid, password, position, environment, waste_type="organic") : 
        """
        Initialize the Bin Agent.

        Args:
            jid (str): The agent's JID.         
            password (str): The agent's password.       
            position (tuple): The location (x, y) in the environment.       
            environment (obj): The shared environment object.       
            waste_type (str, optional): Type of waste. Defaults to "organic".       
        """
        super().__init__(jid, password)
        self.position = position
        self.environment = environment
        self.waste_type = waste_type
        self.max_capacity = 100
        self.current_waste = random.randint(0, int(self.max_capacity * 0.4))
        self.received_responses = {}
        self.accumulation_period = random.randint(5,8)
        self.is_waiting_for_truck = False
        self.sent_colection_request = False
        self.resolving = 0
        self.collection_time = []
        self.waste = None
        self.time = None
        self.counter = 0
        self.overflow_times = []
        self.is_overflowing = False
        self.request_start_time = None
        self.total_collections = 0
        
        # Initialize specific counters
        self.cfp_collections = 0
        self.autonomous_collections = 0
        self.last_collection_type = None
        
        # Variable to control if the current collection has already been counted
        self.collection_counted = False
        self.last_waste_level = self.current_waste 
        
    async def setup(self):
        """Set up the agent's initial behaviours."""
        self.add_behaviour(self.ReceiveProposalBehaviour())
        self.add_behaviour(self.ReceiveProblemBehaviour())
        self.add_behaviour(self.ReceiveProblemResolveBehaviour())
        self.add_behaviour(self.GetBinsTimeBehaviour())

        print(f"[{self.name}] [{self.waste_type}] Initialized with current waste: {self.current_waste} units.")

    async def send_cfp_to_trucks(self):
        """Send a Call For Proposal (CFP) to all available trucks."""
        print(f"[{self.agent.name}] [{self.agent.waste_type}] Attempting to send CFP")
        for truck in self.agent.environment.trucks:
            if not truck.is_busy:
                cfp_message = Message(to = str(truck.jid))
                cfp_message.set_metadata("performative", "cfp")
                # Include waste type in the message body along with position
                cfp_message.body = f"{self.agent.position[0]},{self.agent.position[1]},{self.agent.waste_type}"
                await self.send(cfp_message)
                print(f"[{self.agent.name}] [({self.agent.position[1]},{self.agent.position[0]})] [{self.agent.waste_type}] CFP enviado ao truck {truck.jid}.")
    
        # Adds a waiting behavior to collect responses from trucks
        wait_for_responses=self.agent.WaitForResponsesBehaviour()
        self.agent.add_behaviour(wait_for_responses)
        
    def is_waste_type_compatible(self, truck_type, bin_type):
        """
        Check compatibility between truck type and bin waste type.

        Args:
            truck_type (str): The waste type the truck can collect.         
            bin_type (str): The waste type of the bin.      

        Returns:
            bool: True if compatible, False otherwise.
        """
        """Check if truck waste type is compatible with bin waste type"""       
        if truck_type == "generic":
            return True  # Generic trucks can collect any type
        elif truck_type == "organic" and bin_type == "organic":
            return True
        elif truck_type == "recyclable" and bin_type == "recyclable":
            return True
        return False
    
    async def accept_best_proposal(self, best_proposal):
        """
        Send an acceptance message to the selected truck.

        Args:
            best_proposal (dict): Dictionary containing truck JID and path.         
        """
        accept_msg = Message(to = str(best_proposal['truck_jid']))
        accept_msg.set_metadata("performative", "accept")
        path_str = best_proposal['path']
        accept_msg.body = path_str
        await self.send(accept_msg)
        self.agent.is_waiting_for_truck = True
        self.agent.sent_colection_request = False
        print(f"[{self.agent.name}] [{self.agent.waste_type}] Aceitação enviada ao truck {best_proposal['truck_jid']} ({best_proposal['truck_waste_type']}) com o caminho: {best_proposal['path']}.")
    
    class WasteAccumulationBehaviour(PeriodicBehaviour):
        """Periodically simulate waste accumulation and trigger collection requests."""
        async def run(self):
            """Increment waste level and trigger CFP if threshold is reached."""
            accumulation = random.randint(0, 10)

            if self.agent.max_capacity - self.agent.current_waste < accumulation:
                self.agent.current_waste = self.agent.max_capacity

                if not getattr(self.agent, "is_overflowing", False):
                    self.agent.is_overflowing = True
                    self.agent.overflow_times.append(self.agent.environment.timer())
                    print(f"[{self.agent.name}] [({self.agent.position[1]},{self.agent.position[0]})] [{self.agent.waste_type}] está cheio. Aguardando recolha")

                if not self.agent.sent_colection_request and not self.agent.is_waiting_for_truck:
                    self.agent.sent_colection_request = True
                    self.agent.received_responses = {}
                    # Only set request_start_time if it is NULL (to not overwrite previous CFP times)
                    if self.agent.request_start_time is None:
                        self.agent.request_start_time = self.agent.environment.timer()
                    self.agent.last_collection_type = 'cfp'
                    await self.send_cfp_to_trucks()
                return

            self.agent.current_waste += accumulation
            print(f"[{self.agent.name}] [{self.agent.waste_type}] Waste level : {self.agent.current_waste} / {self.agent.max_capacity}. Accumulation = {accumulation}")

            if self.agent.current_waste < 0.7 * self.agent.max_capacity:
                self.agent.is_overflowing = False
                # Reset CFP request when waste drops below 70%
                self.agent.sent_colection_request = False
                self.agent.is_waiting_for_truck = False

            if self.agent.current_waste >= 0.7 * self.agent.max_capacity:
                self.agent.counter += 1
                if not self.agent.sent_colection_request and not self.agent.is_waiting_for_truck:
                    print(f"[{self.agent.name}] [({self.agent.position[1]},{self.agent.position[0]})] [{self.agent.waste_type}] Waste level reached >= 70%. Sending collection request")
                    self.agent.sent_colection_request = True
                    self.agent.received_responses = {}
                    # Only set request_start_time if it is NULL
                    if self.agent.request_start_time is None:
                        self.agent.request_start_time = self.agent.environment.timer()
                    self.agent.last_collection_type = 'cfp'
                    await self.send_cfp_to_trucks()

    class ReceiveProposalBehaviour(CyclicBehaviour):
        """Listen for proposals or rejections from trucks."""
        async def run(self):
            """Receive messages and store proposals in the agent's memory."""
            msg = await self.receive(timeout=1)
            if msg:
                if msg.metadata.get("performative") == "propose": # Extracts path, cost and available capacity from the truck's proposal
                    path_str, estimated_cost, available_capacity, fuel, truck_waste_type = msg.body.split(";")
                    estimated_cost = int(estimated_cost)
                    available_capacity = int(available_capacity)
                    # Stores the proposal, including the path
                    self.agent.received_responses[msg.sender] = {
                        'type': 'proposal',
                        'cost': estimated_cost,
                        'available_capacity': available_capacity,
                        'fuel': fuel,
                        'path': path_str,
                        'truck_waste_type': truck_waste_type
                    }
                    print(f"[{self.agent.name}] [{self.agent.waste_type}] Proposta recebida de {msg.sender}: Capacidade {available_capacity}, Custo {estimated_cost}, Tipo {truck_waste_type}")
                elif msg.metadata.get("performative") == "decline":
                    # Stores the rejection as a response
                    self.agent.received_responses[msg.sender] = {'type': 'decline'}
                    print(f"[{self.agent.name}] [{self.agent.waste_type}] Rejeição recebida de {msg.sender}")

    class WaitForResponsesBehaviour(OneShotBehaviour):
        """Wait for a fixed time to collect proposals and evaluate the best one."""
        async def run(self):
            """Wait 3 seconds and then trigger proposal evaluation."""
            await asyncio.sleep(3) # wait for trucks responses to be sent
            # Ends the wait when time expires and evaluates proposals
            print(f"[{self.agent.name}] [{self.agent.waste_type}] Tempo de espera expirado. Avaliando propostas...")
            await self.evaluate_proposals() # calls the function to choose the best proposal
            self.agent.received_respondes = {}
            self.kill()  # Ends the behavior after evaluation

        async def evaluate_proposals(self):
            """Select the best proposal based on cost, capacity and fuel level."""
            best_proposal = None
            for truck_jid, response in self.agent.received_responses.items():
                if response['type'] == 'proposal':
                    # get the right truck by its jid
                    for t in self.agent.environment.trucks:
                        if(t.jid == truck_jid):
                            cost, path = t.get_shortest_path(self.agent.position)
                            is_busy = t.is_busy                   
                            # updates the proposal if meanwhile the truck moved during exploration
                            if(is_busy==False and (cost!=response['cost'] or path!=ast.literal_eval(response['path']))):
                                response['cost']=cost
                                response['path']=f"{path}"
                    
                    # Check if truck waste type is compatible with bin waste type
                    is_compatible = self.is_waste_type_compatible(response['truck_waste_type'], self.agent.waste_type)
                    
                    if (not is_busy and is_compatible and
                        (best_proposal is None or                        
                        response['available_capacity'] > best_proposal['available_capacity'] or
                        (response['available_capacity'] == best_proposal['available_capacity'] and response['cost'] < best_proposal['cost']) or
                        (response['available_capacity'] == best_proposal['available_capacity'] and response['cost'] == best_proposal['cost'] and response['fuel'] > best_proposal['fuel']) or
                        (response['available_capacity'] == best_proposal['available_capacity'] and response['cost'] == best_proposal['cost'] and response['fuel'] > best_proposal['fuel']) and response['truck_jid'] < best_proposal['fuel'])):
                        # Updates the best proposal based on capacity and cost
                        best_proposal = {
                            'truck_jid': truck_jid,
                            'cost': response['cost'],
                            'available_capacity': response['available_capacity'],
                            'fuel': response['fuel'],
                            'path': response['path'],
                            'truck_waste_type': response['truck_waste_type']
                        }

            if best_proposal:
                # If there is a valid proposal, send acceptance
                if self.agent.current_waste >= 70:
                    # MARKS THAT THIS COLLECTION WILL BE BY CFP
                    self.agent.last_collection_type = 'cfp'
                    await self.accept_best_proposal(best_proposal)
                else:
                    self.agent.is_waiting_for_truck = False
                    self.agent.sent_colection_request = False

    #1. Detect that there is a problem
    class ReceiveProblemBehaviour(CyclicBehaviour):
        """Listen for problem reports from trucks."""
        # it is cyclic because it is always listening for messages
        async def run(self):
            """Check for 'problem' messages and initiate wait logic."""
            msg = await self.receive(timeout = 1)
            if msg and msg.metadata.get("performative") == "problem": # truck warns bin that there was a problem (e.g., truck that was going to collect that waste got stuck in traffic or broke down)
                # Adds a waiting behavior to collect responses from trucks
                wait_for_problem_responses = self.agent.WaitForProblemResolveBehaviour() # bin creates a waiting behavior
                self.agent.add_behaviour(wait_for_problem_responses) #adds the behavior to itself to start the time count
                print(f"[{self.agent.name}] [{self.agent.waste_type}] O bin detetou problema")
    
    #2. Receive confirmation that someone is resolving
    class ReceiveProblemResolveBehaviour(CyclicBehaviour): 
        """Listen for problem resolution confirmations."""
        #also stays listening for messages continuously
        async def run(self):
            """Check for 'resolve-problem' messages."""
            msg = await self.receive(timeout=1)
            if msg:
                if msg.metadata.get("performative") == "resolve-problem": # if any truck sends this message it means it is resolving the other's problem
                    self.agent.resolving += 1
    
    #3. Wait a while for a resolution, when the bin detects a problem (in 1.) this behavior is activated
    class WaitForProblemResolveBehaviour(OneShotBehaviour):
        """Wait window to see if a problem is resolved."""
        #executes only once - one shot
        async def run(self):
            """Wait 3 seconds to see if the problem is resolved, if not reset request state."""
            await asyncio.sleep(3)
            print(f"[{self.agent.name}] [{self.agent.waste_type}] Tempo de espera para resolução acabou")
            if self.agent.resolving == 0: 
                self.agent.is_waiting_for_truck = False 
                self.agent.sent_colection_request = False #frees itself to accept new requests
            self.agent.resolving = 0 
            self.kill()

    #serves for the bin to measure how long it takes to be collected after reaching a certain waste level
    #meaning, it automatically records the time between being almost full and being emptied
    class GetBinsTimeBehaviour(CyclicBehaviour):
        """Collect metrics about collection times and efficiency."""
        async def run(self):
            """Monitor waste levels to detect collections and record times."""
            waste_decreased = self.agent.current_waste < self.agent.last_waste_level
            
            if waste_decreased and not self.agent.collection_counted:
                self.agent.total_collections += 1
                self.agent.collection_counted = True
                
                if self.agent.last_collection_type == 'cfp':
                    self.agent.cfp_collections += 1
                    print(f"[{self.agent.name}] CFP collection confirmed! Total CFP: {self.agent.cfp_collections}")
                    
                    # Keep request_start_time for multiple CFP collections
                    if hasattr(self.agent, 'request_start_time') and self.agent.request_start_time is not None:
                        collection_duration = self.agent.environment.timer() - self.agent.request_start_time
                        self.agent.collection_time.append(collection_duration)
                        print(f"[{self.agent.name}] CFP collection completed in {collection_duration}s. Times: {self.agent.collection_time}")
                    
                elif self.agent.last_collection_type == 'autonomous':
                    self.agent.autonomous_collections += 1
                    print(f"[{self.agent.name}] Autonomous collection confirmed! Total Autonomous: {self.agent.autonomous_collections}")
                
                print(f"[{self.agent.name}] Collection recorded! Type: {self.agent.last_collection_type}, Total: {self.agent.total_collections}. Waste: {self.agent.last_waste_level} -> {self.agent.current_waste}")
            
            # Reset flag only when waste stops decreasing
            if self.agent.current_waste >= self.agent.last_waste_level:
                self.agent.collection_counted = False
                # Reset request_start_time only when the bin stops being collected
                if self.agent.current_waste < 0.7 * self.agent.max_capacity:
                    self.agent.request_start_time = None
            
            self.agent.last_waste_level = self.agent.current_waste
            await asyncio.sleep(1)