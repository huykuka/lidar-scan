import { useMemo, useRef } from 'react'
import { BufferGeometry, Float32BufferAttribute } from 'three'

export function useMemoizedCloud(points: Float32Array) {
  const geometryRef = useRef(new BufferGeometry())

  useMemo(() => {
    const attribute = new Float32BufferAttribute(points, 3)
    geometryRef.current.setAttribute('position', attribute)
    if (points.length) {
      geometryRef.current.computeBoundingSphere()
    }
  }, [points])

  return geometryRef
}
