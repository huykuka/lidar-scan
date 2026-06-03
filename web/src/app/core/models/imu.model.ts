import {Pose} from './pose.model';

export interface ImuVector3 {
  x: number;
  y: number;
  z: number;
}

export interface ImuQuaternion {
  x: number;
  y: number;
  z: number;
  w: number;
}

export interface ImuSnapshot {
  timestamp: number;
  orientation: ImuQuaternion;
  angular_velocity: ImuVector3;
  linear_acceleration: ImuVector3;
}

export interface ImuCalibrationResponse {
  success: boolean;
  node_id: string;
  pose: Pose;
  imu: ImuSnapshot | null;
}

export interface ImuStatusResponse {
  node_id: string;
  imu_auto_level: boolean;
  has_imu_data: boolean;
  imu: ImuSnapshot | null;
}
