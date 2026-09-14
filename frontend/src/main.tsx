import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./store/auth";
import { InvestigationProvider } from "./store/investigation";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <InvestigationProvider>
          <App />
        </InvestigationProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
