#!/usr/bin/env python3
import os
import signal
import Jetson.GPIO as GPIO
import rclpy
import canopen

from rclpy.node import Node
from geometry_msgs.msg import Twist


## Constants

# Motor IDs
FRONT_LEFT = 1
FRONT_RIGHT = 2
CENTER_LEFT = 3
CENTER_RIGHT = 4
REAR_LEFT = 5
REAR_RIGHT = 6
FRONT_LEFT_ANGLE = 7
FRONT_RIGHT_ANGLE = 8
REAR_LEFT_ANGLE = 9
REAR_RIGHT_ANGLE = 10

MOTOR_IDS = [   FRONT_LEFT, FRONT_RIGHT, CENTER_LEFT,
                CENTER_RIGHT, REAR_LEFT, REAR_RIGHT,
                FRONT_LEFT_ANGLE, FRONT_RIGHT_ANGLE,
                REAR_LEFT_ANGLE, REAR_RIGHT_ANGLE] 


class MotorSubscriber(Node):

    def __init__(self):
        super().__init__('motor_subscriber')
        self.init_settings()
        self.init_CAN_network()
        self.initialize_sdo_objects(self.eds_path)
        self.startup_motors()
        self.init_subscription()

    def init_settings(self):
        # Max linear and angular velocities
        self.max_linear_vel = 2000
        self.max_angular_vel = 400

        # Motor IDs
        self.motor_ids = MOTOR_IDS
        self.velocity_motor_ids = MOTOR_IDS[:6]
        self.steering_motor_ids = MOTOR_IDS[6:]

        # Target velocity and position
        self.target_position = [0] * len(self.motor_ids)

        # EDS path
        self.eds_path = 'install/hardware/share/hardware/config/C5-E-2-09.eds'

    def init_CAN_network(self):
        try:
            self.network = canopen.Network()
            self.network.connect(channel='can1', bustype='socketcan')
            GPIO.setmode(GPIO.BOARD)
        except Exception as e:
            self.get_logger().error(f"Failed to initialize CAN network: {e}")


    def initialize_sdo_objects(self, eds_path):
        '''Initialize SDO objects for the motor controllers'''
        sdo_mapping = {
            'modes_of_operation': 'Modes of operation',
            'target_velocity': 'vl target velocity',
            'modes_display': 'Modes of operation display',
            'status_words': 'Statusword',
            'control_words': 'Controlword',
            'actual_velocity': 0x6044,
            'actual_position': 0x6064
        }

        # Initialize the dictionary to store the actual SDO objects
        self.sdo_objects = {key: [] for key in sdo_mapping.keys()}

        # Initialize empty list of nodes
        self.nodes = []

        try:
            for node_id in self.motor_ids:  #
                current_node = self.network.add_node(node_id, eds_path)
                self.nodes.append(current_node)
                
                for label, sdo_key in sdo_mapping.items():
                    self.sdo_objects[label].append(current_node.sdo[sdo_key])
                    
                #current_node.sdo[0x6060].raw = 8  # Set Mode of Operation to "Cyclic Synchronous Position mode"

        except Exception as e:
            self.get_logger().error(f"Error in initializing SDO objects: {e}")
    def startup_motors(self):
        # Set up velocity motors settings
        for motor_id in (motor_id - 1 for motor_id in self.motor_ids if motor_id < 7):
            try:
                # Set velocity mode
                #self.sdo_objects['modes_of_operation'][motor_id].phys = 0x02
                self.nodes[motor_id].sdo['Modes of operation'].phys = 0x02
                # Set acceleration
                self.nodes[motor_id].sdo['vl velocity acceleration']['DeltaSpeed'].phys = 3500  # TODO - Document what this is
                self.nodes[motor_id].sdo['vl velocity acceleration']['DeltaTime'].phys = 2      # TODO - Document what this is

                # Set deceleration
                self.nodes[motor_id].sdo['vl velocity deceleration']['DeltaSpeed'].phys = 3500  # TODO - Document what this is
                self.nodes[motor_id].sdo[0x6049][0x02].phys = 2     # TODO - Document what this is
                # Max speed
                self.nodes[motor_id].sdo['vl velocity min max amount']['MaxAmount'].phys = 1500             # TODO - Document what this is
                self.nodes[motor_id].sdo['SI unit velocity'].raw   = 0x00B44700            # TODO - Document what this is

                self.get_logger().info(f'Setup settings for motor {motor_id}')     
            except Exception as e:
                self.get_logger().error(f"1: Failed to start up motor {motor_id}: {e}")
        
        # Set up steering motors settings
        for motor_id in (motor_id - 1 for motor_id in self.motor_ids if motor_id > 6):
            try:
                # Set Position mode
                #self.sdo_objects['modes_of_operation'][motor_id].phys = 0x01
                self.nodes[motor_id].sdo['Modes of operation'].phys = 0x01
                # Initialize 
                self.target_position[motor_id] = self.nodes[motor_id].sdo[0x607A]
                
                self.nodes[motor_id].sdo['Profile velocity'].phys = 200 # Profile Velocity
                self.nodes[motor_id].sdo['Profile acceleration'].phys = 350 # Profile Acceleration
                self.nodes[motor_id].sdo['Profile deceleration'].phys = 350 # Profile Deceleration

                self.nodes[motor_id].sdo['Max acceleration'].phys = 700 # Max Acceleration
                self.nodes[motor_id].sdo['Max deceleration'].phys = 700 # Max Deceleration

                self.nodes[motor_id].sdo['Gear ratio']['Motor revolutions'].phys = 62
                self.nodes[motor_id].sdo['Gear ratio']['Shaft revolutions'].phys = 1

                self.get_logger().info(f'Setup settings for motor {motor_id}')      
            except Exception as e:
                self.get_logger().error(f"2: Failed to start up motor {motor_id}: {e}")

        for motor_id in (motor_id - 1 for motor_id in self.motor_ids):
                self.nodes[motor_id].sdo['Controlword'].phys = 0x0006
                if self.nodes[motor_id].sdo['Statusword'].bits[5] == 1 \
                     and self.nodes[motor_id].sdo['Statusword'].bits[9] == 1:
                    self.nodes[motor_id].sdo['Controlword'].phys = 0x0007
                    if self.nodes[motor_id].sdo['Statusword'].bits[1] == 1 \
                            and self.nodes[motor_id].sdo['Statusword'].bits[4] == 1 \
                            and self.nodes[motor_id].sdo['Statusword'].bits[5] == 1 \
                            and self.nodes[motor_id].sdo['Statusword'].bits[9] == 1:
                            self.nodes[motor_id].sdo['Controlword'].phys = 0x000F
                            self.get_logger().info(f'tried starting {motor_id}')     
                    else:
                        self.get_logger().info('2: failed to start motors')
                else:
                    self.get_logger().info('1: failed to start motors')                        

    def init_subscription(self):
        self.subscription = self.create_subscription(
            Twist,
            '/joy_listener/joystic_publisher', # TODO - Change this to the correct topic
            self.listener_callback,
            10)

    def listener_callback(self, msg: Twist):
        '''Callback function for the subscriber'''
        steering_scale = 1000
        velocity_scale = 315
        try:
            #sdf

            for motor, idx in enumerate(self.steer_motor_ids):
                self.control[motor].bits[4] = 0 
                self.target_position[motor].phys = steering_angle[idx] * steering_scale
                self.control[motor].bits[5] = 1
                self.control[motor].bits[4] = 1
            
            for motor, idx in enumerate(self.velocity_motor_ids):
                self.target_velocity[motor].phys = motor_velocities[idx] * velocity_scale

        except Exception as e:
            self.get_logger().error(f"Failed in listener callback: {e}")

    def shutdown_motors(self):
        '''Shutdown the motors'''
        try:
            for motor in self.motor_ids:
                self.control[motor].phys = 0
        except Exception as e:
            self.get_logger().error(f"Failed to shutdown motors: {e}")

def kinematics(linear_vel, angular_vel):
    # Your kinematics logic here...
    # This is a placeholder for now
    pass

if __name__ == "__main__":
    rclpy.init()
    motor_subscriber_node = MotorSubscriber()
    rclpy.spin(motor_subscriber_node)
