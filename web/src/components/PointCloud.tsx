import { useRef, useEffect } from 'react'
import { OrbitControls } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { useLidarStore } from '../state/useLidarStore'
import { useSettingsStore } from '../state/useSettingsStore'
import { useMemoizedCloud } from '../hooks/useMemoizedCloud'

// Default camera/controls configuration
const DEFAULT_CAMERA_POSITION: [number, number, number] = [15, 15, 15]
const DEFAULT_TARGET: [number, number, number] = [5, 5, 5]

function Cloud() {
  const { frame } = useLidarStore()
  const { pointSize, pointColor } = useSettingsStore()
  const geometry = useMemoizedCloud(frame.points)
  
  // Apply rotation to convert Z-up to Y-up coordinate system
  const rotationX = -Math.PI / 2
  const rotationZ = -Math.PI / 2
  
  return (
    <points geometry={geometry.current ?? undefined} rotation={[rotationX, 0, rotationZ]}>
      <pointsMaterial size={pointSize} color={pointColor} sizeAttenuation depthWrite={false} />
    </points>
  )
}

function SceneControls() {
  const controlsRef = useRef<OrbitControlsImpl>(null)
  const { camera } = useThree()
  const { resetNavigation, setResetNavigation } = useSettingsStore()

  useEffect(() => {
    if (resetNavigation && controlsRef.current) {
      // Reset camera position
      camera.position.set(...DEFAULT_CAMERA_POSITION)
      
      // Reset orbit controls target
      controlsRef.current.target.set(...DEFAULT_TARGET)
      controlsRef.current.update()
      
      // Clear the reset flag
      setResetNavigation(false)
    }
  }, [resetNavigation, camera, setResetNavigation])

  return (
    <OrbitControls
      ref={controlsRef}
      target={DEFAULT_TARGET}
      enableDamping
    />
  )
}

export function PointCloud() {
  return (
    <>
      <SceneControls />
      <gridHelper args={[20, 20, '#444444', '#222222']} />
      <axesHelper args={[5]} />
      <Cloud />
    </>
  )
}
