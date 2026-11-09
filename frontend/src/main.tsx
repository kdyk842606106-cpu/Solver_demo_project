import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./prototype.css";
import "./workbench.css";
import "./reference.css";
import "./fidelity.css";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
