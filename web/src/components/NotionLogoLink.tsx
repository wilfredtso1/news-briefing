import React from 'react'
import type { JSX } from 'react/jsx-runtime'



    
// Component

        function NotionLogoLink({
            className,
            logo
        }: {
            className: string;
            logo: React.ReactNode;
        }) {
            return (
                <a className={className}>
                    {logo}
                </a>
            );
        }
    

export default NotionLogoLink
