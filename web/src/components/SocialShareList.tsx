import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import SocialShareButton from './SocialShareButton.tsx'


// Component

        function SocialShareList() {
            return (
                <ul>
                    <ShareItem className={"variant-twitter"} variant="x" />
                    <ShareItem className={"variant-linked-in"} variant="linkedin" />
                    <ShareItem className={"variant-facebook"} variant="facebook" />
                    <ShareItem className={"variant-email"} variant="email" />
                </ul>
            );
        }
    

// Subcomponents

        function ShareItem({ className, variant }: { className: string; variant: string }) {
            return (
                <li className={className}>
                    <SocialShareButton variant={variant} />
                </li>
            );
        }
    

export default SocialShareList
