import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Closed_envelope_mail from './icons/Closed_envelope_mail.tsx'
import Globe_world_network from './icons/Globe_world_network.tsx'
import X_logo from './icons/X_logo.tsx'
import Musical_note from './icons/Musical_note.tsx'
import Linkedin_logo from './icons/Linkedin_logo.tsx'


// Component

        function TemplateDetailLinks() {
            return (
                <ul className={"templateDetail_links__01agD"}>
                    <TemplateDetailLinkItem
                        icon={<Closed_envelope_mail />}
                        label="Email the creator"
                    />
                    <TemplateDetailLinkItem
                        icon={<Globe_world_network />}
                        label="notion.so"
                        rel="nofollow"
                    />
                    <TemplateDetailLinkItem
                        icon={<X_logo />}
                        label="Twitter"
                        rel="nofollow"
                    />
                    <TemplateDetailLinkItem
                        icon={<Musical_note />}
                        label="TikTok"
                        rel="nofollow"
                    />
                    <TemplateDetailLinkItem
                        icon={<Linkedin_logo />}
                        label="LinkedIn"
                        rel="nofollow"
                    />
                </ul>
            );
        }
    

// Subcomponents

        function TemplateDetailLinkItem({
            icon,
            label,
            rel
        }: {
            icon: React.ReactNode;
            label: string;
            rel?: string;
        }) {
            return (
                <li
                    className={"typography_typography__Exx2D"}
                    style={{
                        "--typography-font": "var(--typography-sans-50-medium-font)",
                        "--typography-font-sm": "var(--typography-sans-50-medium-font)",
                        "--typography-letter-spacing": "var(--typography-sans-50-medium-letter-spacing)",
                        "--typography-letter-spacing-sm": "var(--typography-sans-50-medium-letter-spacing)",
                        "--typography-color": "inherit"
                    } as React.CSSProperties}
                >
                    {icon}
                    <a rel={rel}>
                        {label}
                    </a>
                </li>
            );
        }
    

export default TemplateDetailLinks
