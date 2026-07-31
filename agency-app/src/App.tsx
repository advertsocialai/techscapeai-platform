import { useState, useEffect } from "react"
import LoginPage from "./features/auth/pages/LoginPage"
import KnowledgeBasePage from "./features/knowledge-base/pages/KnowledgeBasePage"

function App() {
  const [loggedIn, setLoggedIn] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem("agency_access_token")
    if (token) setLoggedIn(true)
  }, [])

  if (!loggedIn) {
    return <LoginPage onLoginSuccess={() => setLoggedIn(true)} />
  }

  return <KnowledgeBasePage />
}

export default App
