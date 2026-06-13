"use client";

import { cn } from "@/lib/utils";

interface BlueprintIconProps extends React.SVGProps<SVGSVGElement> {
  state?: "" | "thinking" | "working";
}

export function BlueprintIcon({ state = "", className, ...props }: BlueprintIconProps) {
  return (
    <svg
      className={cn("eng-ai-icon", state, className)}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="-10 -10 120 120"
      {...props}
    >
      <style>{`
        /* Global Brand Variables */
        .eng-ai-icon {
          --brand-primary: #00f0ff;    /* Cyan Tech */
          --brand-secondary: #7000ff;  /* Deep Matrix Purple */
          --grid-line: #1e293b;        /* Blueprint Dark Blue */
        }

        /* Core Geometry Structures */
        .structural-axis {
          stroke: var(--grid-line);
          stroke-width: 1.5;
          stroke-dasharray: 4 4;
        }
        
        .vector-frame {
          stroke: url(#tech-gradient);
          stroke-width: 2.5;
          fill: none;
          stroke-linecap: round;
          stroke-linejoin: round;
          transform-origin: 50px 50px;
        }

        .ai-core-node {
          fill: var(--brand-primary);
          filter: drop-shadow(0 0 6px var(--brand-primary));
        }

        .radar-sweep {
          fill: none;
          stroke: var(--brand-primary);
          stroke-width: 1;
          opacity: 0;
          transform-origin: 50px 50px;
        }

        /* ANIMATION STATE: THINKING (Radar/Grid Mapping) */
        .eng-ai-icon.thinking .radar-sweep {
          animation: radarRipple 1.8s cubic-bezier(0.1, 0.8, 0.3, 1) infinite;
        }
        .eng-ai-icon.thinking .ai-core-node {
          animation: corePulse 0.9s ease-in-out infinite alternate;
        }

        /* ANIMATION STATE: WORKING (Pipeline Active Drawing) */
        .eng-ai-icon.working .vector-frame {
          stroke-dasharray: 120;
          stroke-dashoffset: 240;
          animation: blueprintDraw 2s linear infinite;
        }
        .eng-ai-icon.working .structural-axis {
          animation: axisRotate 12s linear infinite;
        }

        /* Keyframe Engine Definitions */
        @keyframes radarRipple {
          0% { r: 5; opacity: 0.8; }
          100% { r: 42; opacity: 0; }
        }
        @keyframes corePulse {
          0% { transform: scale(1); opacity: 0.7; filter: drop-shadow(0 0 3px var(--brand-primary)); }
          100% { transform: scale(1.25); opacity: 1; filter: drop-shadow(0 0 10px var(--brand-primary)); }
        }
        @keyframes blueprintDraw {
          to { stroke-dashoffset: 0; }
        }
        @keyframes axisRotate {
          100% { transform: rotate(90deg); }
        }
      `}</style>

      <defs>
        <linearGradient id="tech-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="var(--brand-primary)" />
          <stop offset="100%" stop-color="var(--brand-secondary)" />
        </linearGradient>
      </defs>

      <g className="structural-axis" transform-origin="50 50">
        <line x1="50" y1="5" x2="50" y2="95" />
        <line x1="5" y1="50" x2="95" y2="50" />
        <circle cx="50" cy="50" r="35" />
      </g>

      <circle className="radar-sweep" cx="50" cy="50" r="5" />
      <circle className="radar-sweep" cx="50" cy="50" r="5" style={{ animationDelay: "0.6s" }} />

      <path
        className="vector-frame"
        d="M 50,14 L 82,32 L 82,68 L 50,86 L 18,68 L 18,32 Z M 50,14 L 50,50 M 82,32 L 50,50 M 82,68 L 50,50 M 50,86 L 50,50 M 18,68 L 50,50 M 18,32 L 50,50"
      />

      <circle className="ai-core-node" cx="50" cy="50" r="4.5" transform-origin="50 50" />
    </svg>
  );
}
