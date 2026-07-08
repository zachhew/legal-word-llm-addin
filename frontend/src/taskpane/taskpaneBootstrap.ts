/*
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT license.
 */

/* global console, document, Office */

import * as React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";

Office.onReady((info) => {
  const rootElement = document.getElementById("container");

  if (!rootElement) {
    console.error("Task pane root container was not found.");
    return;
  }

  if (info.host === Office.HostType.Word) {
    createRoot(rootElement).render(React.createElement(App));
    return;
  }

  rootElement.textContent = "Эта надстройка работает только в Microsoft Word.";
});
