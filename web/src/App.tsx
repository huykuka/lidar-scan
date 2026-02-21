import { Canvas } from '@react-three/fiber'
import { Suspense } from 'react'
import { PointCloud } from './components/PointCloud'
import { TopicPanel } from './components/TopicPanel'
import { useLidarStream } from './hooks/useLidarStream'
import { Layout } from './layout/Layout'
import { Hud } from './components/Hud'

function App() {
  useLidarStream()

  return (
    <Layout>
      <TopicPanel />
      <div className="relative h-[50vh] md:h-full w-full min-h-[400px]">
        <Canvas
          camera={{ position: [15, 15, 15], fov: 75 }}
          resize={{ scroll: false, debounce: { scroll: 50, resize: 50 } }}
          style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
        >
          <color attach="background" args={['#000000']} />
          <Suspense fallback={null}>
            <PointCloud />
          </Suspense>
        </Canvas>
        <Hud />
      </div>
    </Layout>
  )
}

export default App
