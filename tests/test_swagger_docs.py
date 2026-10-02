import shutil
import subprocess
import unittest

from fastapi.testclient import TestClient

from app.docs import CSRF_INTERCEPTOR
from main import app


class SwaggerDocsTests(unittest.TestCase):
    def test_docs_configures_cookie_and_csrf_requests(self):
        with TestClient(app) as client:
            response = client.get("/docs")
            self.assertEqual(response.status_code, 200)
            self.assertIn('"withCredentials": true', response.text)
            self.assertIn("requestInterceptor: swaggerCsrfInterceptor", response.text)
            self.assertIn('const csrfUrl = "/api/users/csrf";', response.text)
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_docs_supports_proxy_prefix(self):
        with TestClient(app, root_path="/finance") as client:
            response = client.get("/docs")
            self.assertIn('const csrfUrl = "/finance/api/users/csrf";', response.text)
            self.assertIn("url: '/finance/openapi.json'", response.text)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the Swagger interceptor test")
    def test_interceptor_refreshes_tokens_and_propagates_errors(self):
        script = """
const assert = require("node:assert/strict");
const window = {location: {href: "http://localhost:8000/docs", origin: "http://localhost:8000"}};
const csrfUrl = "/api/users/csrf";
let calls = 0;
let fail = false;
const fetch = async (url, options) => {
    assert.equal(url, csrfUrl);
    assert.equal(options.credentials, "include");
    assert.equal(options.cache, "no-store");
    calls++;
    return {ok: !fail, json: async () => fail
        ? {detail: "Источник запроса не разрешён"} : {csrf_token: `token-${calls}`}};
};
""" + CSRF_INTERCEPTOR + """
(async () => {
    const login = await swaggerCsrfInterceptor({url: "/api/users/login", method: "POST"});
    assert.equal(login.credentials, "include");
    assert.equal(login.headers["X-CSRF-Token"], "token-1");
    const logout = await swaggerCsrfInterceptor({url: "/api/users/logout", method: "post",
        headers: {"x-csrf-token": "stale", "Content-Type": "application/json"}});
    assert.equal(logout.headers["X-CSRF-Token"], "token-2");
    assert.equal(logout.headers["x-csrf-token"], undefined);
    assert.equal(logout.headers["Content-Type"], "application/json");
    const me = await swaggerCsrfInterceptor({url: "/api/users/me", method: "GET"});
    assert.equal(me.credentials, "include");
    assert.equal(calls, 2);
    const foreign = {url: "https://other.example/api/users/login", method: "POST"};
    assert.deepEqual(await swaggerCsrfInterceptor(foreign), foreign);
    assert.equal(calls, 2);
    fail = true;
    await assert.rejects(swaggerCsrfInterceptor({url: "/api/users/login", method: "POST"}),
        /Источник запроса не разрешён/);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
        result = subprocess.run([shutil.which("node"), "-e", script],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
