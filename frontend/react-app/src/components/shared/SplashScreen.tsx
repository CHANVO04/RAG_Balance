import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'

interface Props {
  onComplete: () => void
}

export default function SplashScreen({ onComplete }: Props) {
  const [nodesReached, setNodesReached] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setNodesReached(true)
    }, 1200)
    return () => clearTimeout(timer)
  }, [])

  return (
    <motion.div
      initial={{ opacity: 1 }}
      animate={{ opacity: 0 }}
      transition={{ duration: 0.6, delay: 3.2, ease: 'easeInOut' }}
      onAnimationComplete={onComplete}
      className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-[#f7f8fc] dark:bg-[#070a13] select-none"
    >
      <div className="relative w-[450px] h-[450px] flex flex-col items-center justify-center">
        {/* Glow Halo 1: Rotating clockwise */}
        <div 
          className="absolute w-72 h-72 rounded-full bg-gradient-to-tr from-blue-600/30 to-cyan-500/20 blur-3xl opacity-60 animate-spin"
          style={{ animationDuration: '24s' }}
        />
        {/* Glow Halo 2: Rotating counter-clockwise */}
        <div 
          className="absolute w-72 h-72 rounded-full bg-gradient-to-bl from-indigo-500/20 to-teal-400/20 blur-3xl opacity-50 animate-spin"
          style={{ animationDuration: '18s', animationDirection: 'reverse' }}
        />

        {/* SVG Neural Connections */}
        <svg viewBox="0 0 200 200" className="w-80 h-80 z-10">
          {/* Paths connecting outer nodes to logo center */}
          {[
            "M 30,30 L 100,100",
            "M 170,30 L 100,100",
            "M 30,170 L 100,100",
            "M 170,170 L 100,100"
          ].map((d, i) => (
            <motion.path
              key={i}
              d={d}
              fill="none"
              stroke="url(#line-grad)"
              strokeWidth="1.5"
              strokeLinecap="round"
              initial={{ pathLength: 0, opacity: 0.2 }}
              animate={{ pathLength: 1, opacity: 0.8 }}
              transition={{ duration: 1.4, ease: 'easeOut', delay: i * 0.15 }}
            />
          ))}

          {/* Core SVG bounding circle */}
          <motion.circle
            cx="100"
            cy="100"
            r="32"
            fill="none"
            stroke="url(#logo-grad)"
            strokeWidth="2.5"
            initial={{ pathLength: 0, rotate: -90 }}
            animate={{ pathLength: 1, rotate: 270 }}
            transition={{ duration: 1.8, ease: 'easeInOut', delay: 0.4 }}
          />

          {/* Gradients */}
          <defs>
            <linearGradient id="line-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.9" />
            </linearGradient>
            <linearGradient id="logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" />
              <stop offset="100%" stopColor="#06b6d4" />
            </linearGradient>
          </defs>
        </svg>

        {/* Floating Glowing Particle Nodes Converging */}
        <div className="absolute inset-0 pointer-events-none z-20">
          {[
            { startX: 60, startY: 60, label: 'Vector' },
            { startX: 390, startY: 60, label: 'Graph' },
            { startX: 60, startY: 390, label: 'Vision' },
            { startX: 390, startY: 390, label: 'LLM' }
          ].map((node, i) => (
            <motion.div
              key={i}
              initial={{ x: node.startX, y: node.startY, scale: 0, opacity: 0 }}
              animate={{ x: 225 - 8, y: 225 - 8, scale: [0, 1.2, 1, 0], opacity: [0, 1, 1, 0] }}
              transition={{ duration: 1.6, ease: 'easeInOut', delay: i * 0.12 }}
              className="absolute w-4 h-4 rounded-full bg-primary flex items-center justify-center shadow-lg shadow-primary/50"
            >
              <div className="w-1.5 h-1.5 rounded-full bg-white" />
              <span className="absolute -bottom-6 text-[8px] font-black uppercase tracking-widest text-primary/95 dark:text-cyan-400 bg-background/80 dark:bg-[#070a13]/80 px-1 py-0.5 rounded border border-primary/20">
                {node.label}
              </span>
            </motion.div>
          ))}
        </div>

        {/* Central Logo Core (SR) - Larger & High contrast */}
        <motion.div
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 180, damping: 14, delay: 1.0 }}
          className="absolute z-30 flex items-center justify-center w-20 h-20 rounded-full bg-white dark:bg-card border-2 border-primary/30 shadow-xl"
        >
          <span className="text-xl font-extrabold tracking-wider bg-gradient-to-tr from-blue-600 to-indigo-600 bg-clip-text text-transparent select-none">
            SR
          </span>
        </motion.div>
      </div>

      {/* Brand title */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 1.4 }}
        className="mt-6 text-center"
      >
        <h2 className="text-2xl font-black tracking-widest text-foreground uppercase select-none">
          Scientific <span className="text-primary font-black">RAG</span>
        </h2>
        <p className="text-[10px] text-muted-foreground/60 uppercase tracking-widest font-extrabold select-none mt-1">
          Decoupled Research Assistant
        </p>
      </motion.div>
    </motion.div>
  )
}
