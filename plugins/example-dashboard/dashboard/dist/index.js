(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const registry = window.__HERMES_PLUGINS__;
  if (!SDK || !registry || typeof registry.register !== "function") return;

  const React = SDK.React;
  const h = React.createElement;
  const { useEffect, useState } = SDK.hooks;
  const C = SDK.components;

  function ExamplePage() {
    const [state, setState] = useState({
      loading: true,
      error: "",
      message: "",
      version: "",
    });

    useEffect(function () {
      let active = true;
      SDK.fetchJSON("/api/plugins/example/hello")
        .then(function (data) {
          if (!active) return;
          setState({
            loading: false,
            error: "",
            message: data && data.message ? String(data.message) : "Example plugin loaded.",
            version: data && data.version ? String(data.version) : "",
          });
        })
        .catch(function (err) {
          if (!active) return;
          setState({
            loading: false,
            error: err && err.message ? String(err.message) : String(err),
            message: "",
            version: "",
          });
        });
      return function () { active = false; };
    }, []);

    return h("div", { className: "flex max-w-2xl flex-col gap-4 p-6" },
      h("div", { className: "flex flex-col gap-1" },
        h("p", { className: "text-[0.7rem] text-midforeground/60" }, "Dashboard plugin fixture"),
        h("h1", { className: "text-2xl font-semibold text-foreground" }, "Example")
      ),
      h(C.Card, null,
        h(C.CardHeader, null,
          h(C.CardTitle, null, "Backend route check")
        ),
        h(C.CardContent, { className: "space-y-3 text-sm text-midforeground/80" },
          state.loading
            ? h("p", null, "Loading example plugin API...")
            : state.error
              ? h("p", { role: "alert", className: "text-red-300" }, state.error)
              : h("div", { className: "space-y-2" },
                  h("p", null, state.message),
                  state.version
                    ? h(C.Badge, null, "v" + state.version)
                    : null
                )
        )
      )
    );
  }

  registry.register("example", ExamplePage);
})();
