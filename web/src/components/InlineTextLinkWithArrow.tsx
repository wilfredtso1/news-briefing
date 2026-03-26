import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import InlineTextLink from './InlineTextLink.tsx'


    
// Component

        function InlineTextLinkWithArrow({
            label
        }: {
            label: string;
        }) {
            return (
                <a
                    className={"InlineTextLink_inlineLink__oN8YM InlineTextLink_colorInherit__oGlTG InlineTextLink_underlineOnHover__J78xW"}
                    target={"_self"}
                >
                    <span className={"InlineTextLink_linkContent__SYI4r"}>
                        {label}
                    </span>
                    <span className={"Arrow_arrow__oVjWc Arrow_arrowAfter__8m7lp"}>
                        →
                    </span>
                </a>
            );
        }
    

export default InlineTextLinkWithArrow
