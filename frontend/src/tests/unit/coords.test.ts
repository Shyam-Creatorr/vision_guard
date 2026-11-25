import { describe, it, expect } from 'vitest';
import {
  canvasPointToNorm1000,
  clampBbox1000,
  computeContainLayout,
  norm1000ToCanvasRect,
} from '../../lib/coords';

describe('Coordinate transform utility (coords.ts)', () => {
  it('computes contain layout with uniform padding without cropping', () => {
    const layout = computeContainLayout(960, 640, 800, 892, 28);
    expect(layout.drawH).toBeCloseTo(640 - 56, 1);
    expect(layout.drawW).toBeLessThan(960 - 56);
    expect(layout.drawX).toBeGreaterThan(28);
  });

  it('round-trips normalized 0-1000 coords <-> canvas pixels accurately', () => {
    const layout = computeContainLayout(960, 640, 1200, 800, 28);
    const rect = norm1000ToCanvasRect([200, 150, 400, 550], layout);
    const topLeft = canvasPointToNorm1000(rect.x, rect.y, layout);
    const botRight = canvasPointToNorm1000(rect.x + rect.w, rect.y + rect.h, layout);
    expect(topLeft.normX).toBeCloseTo(150, 1);
    expect(topLeft.normY).toBeCloseTo(200, 1);
    expect(botRight.normX).toBeCloseTo(550, 1);
    expect(botRight.normY).toBeCloseTo(400, 1);
  });

  it('clamps out-of-range boxes cleanly', () => {
    expect(clampBbox1000([-50, -10, 1200, 1050])).toEqual([0, 0, 1000, 1000]);
  });
});
