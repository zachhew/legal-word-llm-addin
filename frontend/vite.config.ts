import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import fs from "node:fs";
import os from "node:os";
import type { ServerOptions } from "node:https";
import path from "node:path";

const backendProxyTarget = process.env.BACKEND_PROXY_TARGET || "http://127.0.0.1:8000";

function getHttpsOptions(): ServerOptions {
  const certsDir = path.resolve(os.homedir(), ".office-addin-dev-certs");
  const certPath = path.resolve(certsDir, "localhost.crt");
  const keyPath = path.resolve(certsDir, "localhost.key");

  if (!fs.existsSync(certPath) || !fs.existsSync(keyPath)) {
    throw new Error("Office dev certificates were not found. Run: npx office-addin-dev-certs install");
  }

  return {
    key: fs.readFileSync(keyPath),
    cert: fs.readFileSync(certPath),
  };
}

function officeAddinStaticAssetsPlugin() {
  const assetsDir = path.resolve(__dirname, "assets");
  const distDir = path.resolve(__dirname, "dist");

  return {
    name: "office-addin-static-assets",
    configureServer(server) {
      server.middlewares.use("/assets", (request, response, next) => {
        const requestPath = decodeURIComponent((request.url || "").split("?")[0]).replace(/^\/+/, "");
        const filePath = path.resolve(assetsDir, requestPath);

        if (!filePath.startsWith(`${assetsDir}${path.sep}`)) {
          next();
          return;
        }

        fs.stat(filePath, (error, stats) => {
          if (error || !stats.isFile()) {
            next();
            return;
          }

          if (filePath.endsWith(".png")) {
            response.setHeader("Content-Type", "image/png");
          }

          fs.createReadStream(filePath).pipe(response);
        });
      });
    },
    closeBundle() {
      const manifestPath = path.resolve(__dirname, "manifest.xml");
      const distManifestPath = path.resolve(distDir, "manifest.xml");
      const distAssetsPath = path.resolve(distDir, "assets");

      fs.mkdirSync(path.dirname(distManifestPath), { recursive: true });
      fs.copyFileSync(manifestPath, distManifestPath);
      fs.cpSync(assetsDir, distAssetsPath, { recursive: true });
    },
  };
}

export default defineConfig(({ command }) => {
  const httpsOptions = command === "serve" ? getHttpsOptions() : undefined;

  return {
    root: "src/taskpane",
    plugins: [react(), officeAddinStaticAssetsPlugin()],
    publicDir: false,
    server: {
      host: "localhost",
      port: 3000,
      strictPort: true,
      https: httpsOptions,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      },
      proxy: {
        "/backend": {
          target: backendProxyTarget,
          changeOrigin: true,
          rewrite: (proxyPath) => proxyPath.replace(/^\/backend/, ""),
          timeout: 180000,
        },
      },
    },
    preview: {
      host: "localhost",
      port: 3000,
      https: httpsOptions,
    },
    build: {
      outDir: "../../dist",
      emptyOutDir: true,
      rollupOptions: {
        input: {
          taskpane: path.resolve(__dirname, "src/taskpane/taskpane.html"),
          commands: path.resolve(__dirname, "src/taskpane/commands.html"),
        },
      },
    },
  };
});
