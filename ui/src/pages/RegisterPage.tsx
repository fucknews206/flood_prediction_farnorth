// The Register form is now combined into LoginPage.tsx (tab-based).
// This file redirects to the login page with the register tab pre-selected.
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function RegisterPage() {
    const navigate = useNavigate()
    useEffect(() => {
        navigate('/login', { replace: true })
    }, [navigate])
    return null
}
