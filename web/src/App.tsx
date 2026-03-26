import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

import LandingPage from './pages/LandingPage';
import SetupPage from './pages/SetupPage';
import ConfirmPage from './pages/ConfirmPage';
import AccountPage from './pages/AccountPage';
import UnsubscribePage from './pages/UnsubscribePage';

import './global.css';

function App() {
    return (
        <Router>
            <body>
                <Routes>
                    <Route path="/" element={<LandingPage />} />
                    <Route path="/setup" element={<SetupPage />} />
                    <Route path="/confirm" element={<ConfirmPage />} />
                    <Route path="/account" element={<AccountPage />} />
                    <Route path="/unsubscribe" element={<UnsubscribePage />} />
                </Routes>
            </body>
        </Router>
    );
}

export default App
