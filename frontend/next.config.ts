import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * Trace the modules the server actually reaches and emit them beside it, so
   * a runtime image carries those rather than the 698 MB a full install
   * leaves behind.
   *
   * Additive: the ordinary build output is still produced, so `next start`
   * keeps working and the browser test is unaffected. What this adds is
   * `.next/standalone`, whose entry point is `node server.js` rather than the
   * Next CLI.
   */
  output: "standalone",
};

export default nextConfig;
